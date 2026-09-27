# Инженерное заключение: прогон jarvis-policy-20260926

## План
- Статус: `rejected`
- Хеш расписания: `b3b13947bd302803d3cbc641edf7ff0f2222606ebc7dd158cb762adf4ba9e719`
- Стратегия: `не записана`; seed: `не записан`.
- Происхождение/основание выбора: single-policy-pass-on-real-baseline-feedback.

## Расчёт и допуск
- OPM: `OK`; sound: `False`.
- Динамические нарушения: 785; блокирующие: 165.
- Прогноз суррогата: не записан.
- ЧДД после проверки OPM: не записан.
- Вывод: **Отклонён. План не рекомендован к применению.**

## Физические проверки
- Admissible: not recorded; blocking checks: not recorded; warnings: not recorded.
- there is no physics report: the directory /Users/kaifarikman/hackathons/aios-hackv2/out/jarvis-evidence-20260926/runs/jarvis-policy-20260926/validation holds no physics*.json file, so the admissibility of the response is unknown

## Проверки ограничений
- infrastructure.bhp_limits: checked; violations=0; blocking=True; enforcement=None; detail=bottomhole pressure corridor 50.0...300.0 bar: lower limit for producers infrastructure.bhp_producer_min_bar, source organizer (organizers' condition), case case not from a file; upper limit for injectors infrastructure.bhp_injector_max_bar, source organizer (organizers' condition), case case not from a file
- infrastructure.compensation: checked; violations=224; blocking=False; enforcement=diagnostic; detail=compensation corridor 0.85...1.15, mode diagnostic: C(k) = injection / withdrawal checked over the field on 224 steps under surface conditions; the formation volume factors B_o/B_w were not supplied to the validator: C(k) is computed under surface conditions, conversion to reservoir conditions was not performed
- infrastructure.compensation_scope: checked; violations=224; blocking=False; enforcement=diagnostic; detail=infrastructure.compensation_scope = 'field_and_groups': the corridor 0.85...1.15 was checked per group under surface conditions, split cf41ef7f9b79301a6f98f6f5dec9a67050e361fad2f73021352bcc268dc87e49 of 1 groups, 224 step-group pairs; the formation volume factors B_o/B_w were not supplied to the validator: C(k) is computed under surface conditions, conversion to reservoir conditions was not performed
- infrastructure.field_pressure: not_set; violations=None; blocking=False; enforcement=None; detail=neither infrastructure.pressure_floor_bar nor infrastructure.pressure_ceiling_bar is set in the case: reservoir pressure was not checked, and a limit must not be assigned on behalf of the organizers
- infrastructure.region_pressure: not_set; violations=None; blocking=False; enforcement=None; detail=neither infrastructure.region_pressure_floor_bar nor infrastructure.region_pressure_ceiling_bar is set in the case: regional reservoir pressure was not checked, and a limit must not be assigned on behalf of the organizers
- infrastructure.water_supply: checked; violations=165; blocking=True; enforcement=None; detail=reinjection fraction 1.0, lag 0 steps, external inflow 0.0 m3/day: injection checked against the water balance on 224 steps
- injection_limits: not_set; violations=None; blocking=False; enforcement=None; detail=injection_limits are not set in the case: the upper limit of total injection by year was not checked
- liquid_limits: not_set; violations=None; blocking=False; enforcement=None; detail=liquid_limits are not set in the case: the upper limit of total liquid production by year was not checked
- material_balance: not_set; violations=None; blocking=False; enforcement=None; detail=the field series FOIP/FWIP/FOPT/FWPT/FWIT were not supplied: the reservoir material balance was not checked
- oil_limits: not_set; violations=None; blocking=False; enforcement=None; detail=oil_limits are not set in the case: the upper limit of total oil production by year was not checked
- production_floors: not_set; violations=None; blocking=False; enforcement=None; detail=production_floors are not set in the case: the lower bound of total oil production by year was not checked
- watercut_limits: not_set; violations=None; blocking=False; enforcement=None; detail=watercut_limits are not set in the case: watercut was not checked
- well_outages: not_set; violations=None; blocking=False; enforcement=None; detail=well_outages are not set in the case: well operation inside outage windows was not checked
- well_outages (static): not_set; violations=None; blocking=True; enforcement=None; detail=well_outages are not set in the case: the static check of events inside outage windows was not run

## Источники
- [manifest.json](/api/jarvis/run-artifacts/jarvis-policy-20260926/manifest)
- [validation/result.json](/api/jarvis/run-artifacts/jarvis-policy-20260926/validation)
- [validation/constraints_report.json](/api/jarvis/run-artifacts/jarvis-policy-20260926/constraints)
- [economics/result.json](/api/jarvis/run-artifacts/jarvis-policy-20260926/economics)
- [economics/npv-table.json](/api/jarvis/run-artifacts/jarvis-policy-20260926/npv-table)
