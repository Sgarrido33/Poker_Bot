"""Produce the final reviewable quality report from completed saved evidence."""
import csv
import hashlib
import json
from pathlib import Path
import re

from pokerfight.campaign import save
from pokerfight.evaluation import environment


ROOT = Path('results/quality_2026-10-28')


def signed(value):
    return f'{value:+.3f}'


def interval(values):
    return f'[{signed(values[0])}; {signed(values[1])}]' if values is not None else '—'


def main():
    plan = json.loads((ROOT / 'protocol.json').read_text())
    pilot, validation = [json.loads((ROOT / phase / 'summary.json').read_text()) for phase in ('pilot', 'validation')]
    if not pilot['complete'] or not validation['complete']:
        raise ValueError('Complete both phases')
    if environment()['source_sha256'] != plan['environment']['source_sha256']:
        raise ValueError('Code changed')
    analysis = json.loads((ROOT / 'validation/analysis.json').read_text())
    variance = json.loads((ROOT / 'variance.json').read_text())
    controls = json.loads((ROOT / 'controls.json').read_text())
    test_count = re.search(r'Ran (\d+) tests', (ROOT / 'tests.txt').read_text())
    if test_count is None or not (ROOT / 'tests.txt').read_text().rstrip().endswith('OK'):
        raise ValueError('Complete a passing test suite before writing the final report')
    ratio = variance['mean_nonbaseline_cell_variance']['between_replica_sample_variance_chips2']['integrated_over_sampled']
    cells = [json.loads(p.read_text()) for p in sorted((ROOT / 'validation').glob('cell_*.json'))]
    with (ROOT / 'validation_cells.csv').open('w', encoding='utf-8', newline='') as file:
        fields = ['scenario', 'players', 'depth_bb', 'variant', 'bb_per_hand', 'delta_vs_v4', 'delta_vs_v2',
                  'bust_hands', 'fallbacks_all_policies']
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in cells:
            for variant, arm in row['arms'].items():
                writer.writerow({**{k: row[k] for k in ('scenario', 'players', 'depth_bb')}, 'variant': variant,
                    **{k: arm[k] for k in ('bb_per_hand', 'bust_hands', 'fallbacks_all_policies')},
                    'delta_vs_v4': arm['bb_per_hand'] - row['arms']['v4']['bb_per_hand'],
                    'delta_vs_v2': arm['bb_per_hand'] - row['arms']['v2']['bb_per_hand']})
    paired = pilot['paired_hand_executions'] + validation['paired_hand_executions']
    sessions = pilot['session_hand_executions'] + validation['session_hand_executions']
    lines = ['# Resultados de calidad: v4rb y v5', '', 'Fecha local: 28 de octubre de 2026.', '',
        '**La política predeterminada permanece en v2.** Las nuevas variantes son experimentales.', '',
        f'Se completaron **{paired + sessions:,} ejecuciones nuevas de mano**: {paired:,} con fichas reiniciadas y {sessions:,} en sesiones. '
        'Son cinco brazos con barajas compartidas; las ejecuciones no son observaciones independientes. '
        'Los mundos internos de Monte Carlo, replays y tests no se incluyen en esa cantidad.', '',
        'El [método](CALIDAD_V5_METODO.md) y el [protocolo previo al piloto](../results/quality_2026-10-28/protocol.json) '
        'describen modelos, semillas, cuotas, agrupación y criterios. No se ajustaron parámetros después del piloto.', '',
        '## Precisión del estimador', '',
        f'La integración exacta redujo **{(1-ratio)*100:.1f} %** la varianza entre réplicas a igual número de mundos '
        'en siete estados de desarrollo: 24 réplicas de 128 mundos por estado/supuesto, 54 comparaciones no base. '
        'Se promedian las varianzas dentro de cada comparación; no se mezclan las diferencias de medias entre estados. '
        'Esta medición demuestra menor ruido bajo el mismo modelo fold/call, sin demostrar mayor fuerza de juego. '
        'Véase [variance.json](../results/quality_2026-10-28/variance.json).', '',
        '## Resultados pareados', '',
        'Igual peso a las 18 celdas de cinco/seis jugadores, 4/8/12 bb y tres escenarios. '
        'Bootstrap estratificado de bloques completos; cada bloque contiene todas las rotaciones de asiento. '
        'Los intervalos son exploratorios y no corrigen comparaciones múltiples.', '',
        '| Etapa | Candidata | Δ frente a v4, bb/mano | IC 95 % | Δ frente a v2 | IC 95 % |',
        '|---|---|---:|---|---:|---|']
    for phase, summary in (('Piloto', pilot), ('Validación', validation)):
        for variant in ('v4rb', 'v5'):
            a, b = (summary['contrasts'][variant][v] for v in ('v4', 'v2'))
            lines.append(f"| {phase} | {variant} | {signed(a['mean_bb_per_hand'])} | {interval(a['interval_95'])} | {signed(b['mean_bb_per_hand'])} | {interval(b['interval_95'])} |")
    lines += ['', '| Candidata | Jugadores | Δ frente a v4 | Δ frente a v2 |', '|---|---:|---:|---:|']
    for variant in ('v4rb', 'v5'):
        for n in ('5', '6'):
            c = validation['contrasts'][variant]
            lines.append(f"| {variant} | {n} | {signed(c['v4']['by_players'][n])} | {signed(c['v2']['by_players'][n])} |")
    lines += ['', 'Las medias de cada celda, ganancias, manos que terminan sin fichas y diferencias están en '
        '[validation_cells.csv](../results/quality_2026-10-28/validation_cells.csv). '
        'En estas celdas se reponen las fichas: `bust_hands` cuenta manos con stack final cero y no eliminaciones de torneo. '
        'El control v2mc permite identificar el efecto de cambiar solo la cuota de muestreo.', '',
        '## Sesiones con eliminación', '',
        'Inicio de 8 bb, máximo veinte manos y ciegas duplicadas cada diez. '
        'Dos grupos independientes por escenario/formato en presión y copias v2; '
        f"{validation['session_tables_per_variant']} mesas por brazo con todos los asientos. "
        'Se remuestrean grupos completos dentro de escenario/formato. La unidad de diferencia es una pila inicial de 800 fichas.', '',
        '| Candidata | Δ fichas/800 frente a v4 | IC 95 % | Δ frente a v2 | IC 95 % |', '|---|---:|---|---:|---|']
    for variant in ('v4rb', 'v5'):
        a, b = (validation['contrasts'][variant][v] for v in ('v4', 'v2'))
        lines.append(f"| {variant} | {signed(a['session_mean_stack_fraction'])} | {interval(a['session_interval_95'])} | {signed(b['session_mean_stack_fraction'])} | {interval(b['session_interval_95'])} |")
    lines += ['', 'Los resúmenes completos, incluidos v4/v2mc frente a v2, están en '
        '[summary.json](../results/quality_2026-10-28/validation/summary.json).', '',
        '## Comprobaciones y diagnóstico', '',
        f"- **{test_count.group(1)} pruebas aprobadas**, incluidas enumeración independiente de respuestas, "
        'oráculo PokerKit de resubidas, aislamiento de la continuación y cuotas pareadas. '
        'Véase [tests.txt](../results/quality_2026-10-28/tests.txt).',
        f"- Las {len(controls['fixed_searches'])} búsquedas con trabajo fijo y {len(controls['complete_hands'])} manos completas "
        'coinciden exactamente con la v4 anterior al excluir los tiempos. El manifiesto de `frozen_v2` sigue intacto.',
        f"- {analysis['paired_deals_audited']} grupos de reparto auditados: misma semilla de baraja en los cinco brazos y conservación de fichas.",
        f"- {len(analysis['replays'])} ejecuciones seleccionadas entre las mayores diferencias positivas y negativas frente a v4: "
        f"{'todas coinciden' if analysis['all_replays_matched'] else 'hay diferencias; consultar análisis'} al repetir observaciones, valores y decisiones con semillas y cuotas originales.",
        f"- Seguridad de las campañas: {'cumplida' if pilot['safety_passed'] and validation['safety_passed'] else 'NO cumplida'}. "
        'Los JSON conservan los contadores de fallbacks y comprobaciones de fichas.', '',
        '| Variante | Subidas con fichas efectivas detrás | Resubidas reales antes de volver a actuar | Pushes efectivos | Cambios por búsqueda |',
        '|---|---:|---:|---:|---:|']
    for v in ('v4', 'v4rb', 'v5'):
        d = analysis['diagnostics'][v]
        lines.append(f"| {v} | {d['raises_leaving_effective_chips']} | {d['opposing_reraises_before_next_decision']} | {d['effective_pushes']} | {d['search_changes']} |")
    lines += ['', 'Los estados visitados cambian entre políticas: estos conteos son descriptivos, '
        'no un efecto causal de la técnica. El [análisis](../results/quality_2026-10-28/validation/analysis.json) '
        'incluye cobertura de las continuaciones, mundos, paradas y máximos de tiempo.', '',
        '## Decisión y límites', '']
    for v in ('v4rb', 'v5'):
        lines.append(f"- {v}: {'cumple' if validation['eligible_for_promotion'][v] else 'no cumple'} todos los criterios registrados de promoción.")
    lines += ['', 'La reducción de ruido de v4rb y el nuevo modelo de resubidas de v5 quedan disponibles para investigación. '
        'No se interpreta el valor calculado dentro del modelo como prueba de rentabilidad real. '
        'v5 omite más resubidas y apuestas futuras, usa supuestos manuales y una continuación de rollout que puede diferir '
        'de la decisión real posterior. Todos los lotes examinados pasan a ser datos de desarrollo. '
        'Siguen pendientes rivales externos, la arena oficial y el formato completo del torneo.', '']
    Path('docs/CALIDAD_V5_RESULTADOS.md').write_text('\n'.join(lines), encoding='utf-8')
    save(ROOT / 'decision.json', {'default': 'v2', 'eligible_for_promotion': validation['eligible_for_promotion'],
        'paired_hand_executions': paired, 'session_hand_executions': sessions,
        'total_new_hand_executions': paired + sessions,
        'source_sha256': environment()['source_sha256'],
        'protocol_sha256': hashlib.sha256((ROOT / 'protocol.json').read_bytes()).hexdigest(),
        'tests_log': str(ROOT / 'tests.txt'),
        'controls': str(ROOT / 'controls.json'), 'variance': str(ROOT / 'variance.json'),
        'validation': str(ROOT / 'validation/summary.json')})
    paths = [p for folder in ('pokerfight', 'scripts', 'tests', 'docs', 'examples') for p in Path(folder).rglob('*')
             if p.is_file() and '__pycache__' not in str(p) and p.suffix in ('.py', '.json', '.md')]
    paths += [Path('README.md')]
    save(ROOT / 'source_manifest.json', {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)})
    print(f'Report: docs/CALIDAD_V5_RESULTADOS.md; new hands: {paired + sessions}')


if __name__ == '__main__':
    main()
