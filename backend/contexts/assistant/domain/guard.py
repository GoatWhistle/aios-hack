from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from math import floor, log10
from typing import Any, Iterable, Mapping, Sequence

NUMBER_PATTERN = re.compile(
    r"(?<![\w.,])[-−]?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?(?![\w])"
    r"|(?<![\w.,])[-−]?\d+(?:[.,]\d+)?(?![\w])"
)
DATE_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{2}\.\d{2}\.\d{4}\b"
    r"|\b(?:(?:in|during|on)\s+)?(?:19|20)\d{2}\s*(?:year|год|года|году|г\.|г\b)"
    r"|\b(?:in|during|on|в|за)\s+(?:19|20)\d{2}\b"
    r"|\b(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)[а-яё]*\s+(?:19|20)\d{2}"
    r"|\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+(?:19|20)\d{2}",
    re.IGNORECASE,
)
RULE_PATTERN = re.compile(r"\bR[0-7]\b|\bR\d+\b")
POSITIVE_PLAN_STATUS = re.compile(
    r"(?:план|расписани\w*).{0,80}(?:допущен\w*|допустим\w*|принят\w*|"
    r"прош[её]л\s+(?:все\s+)?провер\w*|соответствует\s+ограничен\w*)|"
    r"(?:plan|schedule).{0,80}(?:approved|accepted|admissible|(?:is\s+)?sound|passed\s+(?:the\s+)?checks?|"
    r"within\s+(?:the\s+)?constraints?)|\bsound\s*=\s*true\b",
    re.IGNORECASE,
)
NEGATIVE_PLAN_STATUS = re.compile(
    r"(?:план|расписани\w*).{0,80}(?:отклон[её]н\w*|не\s+прош[её]л\w*\s+провер\w*|"
    r"не\s+допущен\w*|не\s+принят\w*)|"
    r"(?:plan|schedule).{0,80}(?:rejected|failed\s+(?:the\s+)?checks?|not\s+accepted|"
    r"not\s+admissible|unsound)|\bsound\s*=\s*false\b",
    re.IGNORECASE,
)
PLAN_STATUS_NEGATION = re.compile(
    r"\b(?:не|нет|нельзя|непринят\w*|отклон[её]н\w*|not|never|isn't|wasn't|"
    r"failed|rejected|unsound)\b",
    re.IGNORECASE,
)
PLAN_STATUS_CLAUSE_BOUNDARY = re.compile(
    r"[;.!?]+|,?\s+(?:but|however|and|while|whereas|although|yet|но|однако|и|а|хотя)\b|,\s*",
    re.IGNORECASE,
)
UNSUPPORTED_DECISION_CLAIM = re.compile(
    r"\b(?:потому\s+что|так\s+как|поскольку|из-за|вызва\w*|прив[её]л\w*\s+к|привод\w*\s+к|"
    r"обуслов\w*|повлия\w*\s+(?:на|в)|влия\w*\s+(?:на|в)|поэтому|вследствие|следстви\w*|благодаря|за\s+сч[её]т|"
    r"в\s+результате|объясня\w*ся|объясня\w*\s+почему|основан\w*\s+на|исходя\s+из|способств\w*|"
    r"(?:ключев\w*|главн\w*|основн\w*)\s+фактор\w*\s+(?:изменени|выбор|рост|снижени)\w*|"
    r"(?:послужил\w*|стала|является)\s+(?:причин\w*|основани\w*)|"
    r"объясня\w*\s+(?:выбор|решени|изменени|динамик|результат|рост|снижени)\w*|"
    r"позвол\w*|застав\w*|превосход\w*|оптимальн\w*|идеальн\w*|наилучш\w*|лучш\w*|эффективн\w*|выгодн\w*|прибыльн\w*|"
    r"максимизир\w*|максимальн\w*|наибольш\w*|более\s+(?:эффективн\w*|выгодн\w*|прибыльн\w*)|"
    r"предпочтительн\w*\s+(?:вариант\w*|план\w*))\b|"
    r"\b(?:because|due\s+to|due\s+in\s+part\s+to|because\s+of|caus(?:e[sd]?|ing|al(?:ly)?)|"
    r"attribut(?:e[sd]?\s+to|able\s+to)|account(?:s|ed)?\s+for|responsible\s+for|"
    r"trigger(?:s|ed|ing)?|dr(?:ive|ives|iven|ove|iving)|determined|motivated|influenced|"
    r"enabled|facilitat(?:e[sd]?|ing)|prompt(?:s|ed|ing)|"
    r"based\s+(?:on|upon)|grounded\s+in|guided\s+by|follows?\s+from|"
    r"contribut(?:e[sd]?|ing)\s+to|impact(?:s|ed|ing)?\s+on|"
    r"affect(?:s|ed|ing)?|influenc(?:e[sd]?|ing)|"
    r"(?:has|have|had)\s+an?\s+effect\s+on|effect(?:s)?\s+on|"
    r"led\s+to|result(?:ed|ing)\s+in|result(?:ed|ing)\s+from|"
    r"as\s+a\s+result|as\s+a\s+consequence|consequence\s+of|gave\s+rise\s+to|"
    r"driv(?:e[sn]?|en|ing)\s+by|thanks\s+to|"
    r"which\s+is\s+why|(?:is|was)\s+(?:the\s+)?reason|(?:is|was)\s+why|"
    r"explains?\s+(?:the\s+)?(?:choice|decision|selection|change|rate|result|trend)|"
    r"explains?\s+the\s+selected\s+rate|"
    r"stem(?:s|med|ming)\s+from|aris(?:es|e|ing)\s+from|explains?\s+why|"
    r"(?:key|main|primary|driving)\s+driver\s+(?:of|behind)|(?:key|main|primary)\s+factor\s+(?:behind|for)|"
    r"therefore|optimal|optimally|optimi[sz](?:e[sd]?|ing)|maximi[sz](?:e[sd]?|ing)|"
    r"most\s+effective|most\s+profitable|more\s+(?:effective|efficient|profitable|valuable)|"
    r"superior|outperform(?:s|ed|ing)?|dominat(?:e[sd]?|ing)|dominant|"
    r"beats?\s+(?:the\s+)?(?:alternative|plan|option|baseline|candidate)|"
    r"wins?\s+over\s+(?:the\s+)?(?:alternative|plan|option|baseline|candidate)|"
    r"highest\s+(?:npv|return|profitability)|top[- ]performing|"
    r"best[- ](?:performing|decision|choice|option|plan)|"
    r"better\s+(?:decision|choice|option|plan)|(?:is|was|performs?)\s+better)\b",
    re.IGNORECASE,
)
DECISION_CLAIM_NEGATION = re.compile(
    r"\b(?:не(?!\s+только\b)|нет|не\s+может|нельзя|не\s+доказывает|не\s+устанавливает|"
    r"not(?!\s+only\b)|never|cannot|can't|doesn't|does\s+not|no\s+evidence)\b",
    re.IGNORECASE,
)
DECISION_CLAUSE_BOUNDARY = re.compile(
    r"[;:!?]+|,?\s+(?:but|however|and|while|whereas|although|yet|но|однако|и|а|хотя)\b|"
    r",?\s+(?:при\s+этом|тогда\s+как)\b",
    re.IGNORECASE,
)
DECISION_NEGATION_SCOPE = 3


def _decision_claim_is_negated(clause: str, claim: re.Match[str]) -> bool:
    """Only let a nearby negation scope over a decision claim.

    A negation elsewhere in the clause (for example, "no evidence ... which
    proves it is the best plan") must not suppress an independent assertion.
    """
    prefix = clause[: claim.start()]
    prior_words = list(re.finditer(r"\b[\w’'-]+\b", prefix, re.UNICODE))
    scoped_prefix = prefix[prior_words[-DECISION_NEGATION_SCOPE - 1].start() :] if len(prior_words) > DECISION_NEGATION_SCOPE else prefix
    return DECISION_CLAIM_NEGATION.search(scoped_prefix) is not None
TOOL_SUCCESS_CLAIM = re.compile(
    r"\b(?:found|generated|created|completed|built|plotted|retrieved|returned|loaded|"
    r"shows|contains|mapped|compared|calculated)\b|\bhere\s+(?:is|are)\b|"
    r"(?:наш[её]л\w*|найден\w*|сгенерир\w*|сформир\w*|создал\w*|создан\w*|"
    r"выполн\w*|постро\w*|загруз\w*|показ\w*|содерж\w*|сопостав\w*|"
    r"рассчитал\w*|готов\w*|получен\w*)",
    re.IGNORECASE,
)
TOOL_SUBJECT_PATTERNS = {
    "draft_case": re.compile(r"\b(?:case|draft|proposal)\b|кейс\w*|черновик\w*|предложен\w*", re.IGNORECASE),
    "draft_alternative": re.compile(r"\b(?:alternative|draft|proposal)\b|альтернатив\w*|черновик\w*|предложен\w*", re.IGNORECASE),
    "council_step": re.compile(
        r"\b(?:council|allocation|quota)\b|совет\w*|квот\w*|распредел\w*", re.IGNORECASE
    ),
    "physics_report": re.compile(
        r"\bphysics\b|\bvalidation\b|физическ\w*|валидац\w*", re.IGNORECASE
    ),
    "system_map": re.compile(
        r"\bsystem map\b|\barchitecture\b|карта системы|архитектур\w*", re.IGNORECASE
    ),
    "case_constraints": re.compile(
        r"\bconstraints?\b|\blimits?\b|ограничен\w*|лимит\w*", re.IGNORECASE
    ),
    "decision_journal": re.compile(
        r"\bdecision journal\b|\bdecision\b|\bcommands?\b|журнал решений|решени\w*|команд\w*",
        re.IGNORECASE,
    ),
    "explain_decision": re.compile(
        r"\bdecision\b|\brules?\b|\bcommands?\b|решени\w*|правил\w*|команд\w*",
        re.IGNORECASE,
    ),
    "connectivity": re.compile(
        r"\bconnectivity\b|\bconnections?\b|\bneighbou?rs?\b|связ\w*|сосед\w*",
        re.IGNORECASE,
    ),
    "well_snapshot": re.compile(
        r"\bwell snapshot\b|\bsnapshot\b|снимок скважин\w*|состояни\w* скважин\w*",
        re.IGNORECASE,
    ),
    "well_series": re.compile(
        r"\btime.series\b|\bseries\b|\bplot\b|временн\w* ряд|график\w*|ряд\w*",
        re.IGNORECASE,
    ),
    "rank_wells": re.compile(
        r"\brank(?:ing)?\b|\branked\b|рейтинг\w*|ранжирован\w*", re.IGNORECASE
    ),
    "compare_wells": re.compile(
        r"\bwell comparison\b|\bcompare wells\b|\bcompared wells\b|сравнен\w* скважин\w*",
        re.IGNORECASE,
    ),
    "field_metrics": re.compile(
        r"\bfield metrics?\b|\bmetrics? of the field\b|показател\w* фонд\w*|метрик\w* фонд\w*",
        re.IGNORECASE,
    ),
    "field_events": re.compile(
        r"\bfield events?\b|\bevents?\b|событи\w* фонд\w*|событи\w*",
        re.IGNORECASE,
    ),
    "find_patterns": re.compile(
        r"\b(?:patterns?|findings?|anomal(?:y|ies))\b|паттерн\w*|находк\w*|аномал\w*",
        re.IGNORECASE,
    ),
    "rule_impact": re.compile(
        r"\brule impact\b|\brule contribution\b|\buplift\b|вклад\w* правил\w*|эффект\w* правил\w*",
        re.IGNORECASE,
    ),
    "compare_scenarios": re.compile(
        r"\bscenario comparison\b|\bcompare scenarios\b|сравнен\w* сценар\w*",
        re.IGNORECASE,
    ),
    "explain_term": re.compile(
        r"\bdefinition\b|\bmeaning\b|\bterm\b|определен\w*|значени\w* термин\w*|термин\w*",
        re.IGNORECASE,
    ),
    "platform_guide": re.compile(
        r"\bguide\b|\binstructions?\b|\bhow to use\b|справк\w*|инструкц\w*|руководств\w*",
        re.IGNORECASE,
    ),
    "run_status": re.compile(
        r"\brun status\b|\bacceptance\b|\badmissible\b|\bplan status\b|статус прогон\w*|допуск план\w*",
        re.IGNORECASE,
    ),
    "submission_summary": re.compile(
        r"\bsubmission package\b|\bpackage for submission\b|пакет сдач\w*|сдаваем\w* пакет",
        re.IGNORECASE,
    ),
    "search_docs": re.compile(
        r"\b(?:documents?|sources?)\b|\bdocument search\b|документ\w*|источник\w*",
        re.IGNORECASE,
    ),
    "system_status": re.compile(
        r"\bsystem status\b|\bstatus board\b|\bchampion\b|\blatest run\b|состояни\w* систем\w*|чемпион\w*",
        re.IGNORECASE,
    ),
    "run_history": re.compile(
        r"\brun history\b|\bhistory of runs\b|истори\w* прогон\w*|список прогон\w*",
        re.IGNORECASE,
    ),
    "run_detail": re.compile(
        r"\brun detail\b|\bmanifest\b|\bvalidation report\b|манифест\w*|детал\w* прогон\w*",
        re.IGNORECASE,
    ),
    "compare_runs": re.compile(
        r"\bcompare runs\b|\bcomparison of runs\b|сравнен\w* прогон\w*|разниц\w* прогон\w*",
        re.IGNORECASE,
    ),
}
WELL_PATTERN = re.compile(
    r"(?:скважин\w*|well)\s*(?:№|#)?\s*[-—–]?\s*(\d+)", re.IGNORECASE
)
STEP_REFERENCE_PATTERN = re.compile(
    r"\b(?:control[_ ]step|step|шаг(?:е|а|у|ом)?)\s*(?:№|#|=)?\s*(\d+)\b",
    re.IGNORECASE,
)
SIGNIFICANT_DIGITS = 2
RELATIVE_TOLERANCE = 5e-3
FENCE_PATTERN = re.compile(r"```[^\n]*\n(.*?)(?:```|\Z)", re.DOTALL)
WHITESPACE_PATTERN = re.compile(r"\s+")
CODE_WARNING_CODE = "code-unverified"
MIN_CODE_LENGTH = 3
_RUN_ID_FIELDS = frozenset({
    "run_id", "source_run_id", "feedback_source_run_id", "evaluation_run_id",
    "run_a", "run_b",
})
_RUN_REFERENCE_PATTERN = re.compile(
    r"\b(?:run(?:[_ -]id)?|прогон(?:а|у|е|ом)?)\s*(?:[:=#]\s*)?`?"
    r"([A-Za-zА-Яа-я](?=[\w-]*-|[\w-]*\d{4})[\w-]*)",
    re.IGNORECASE,
)
_UNIT_FIELD_PATTERNS = {
    "currency_per_volume": re.compile(r"(?:^|_)(?:rub|currency)_per_(?:m3|m³|volume)(?:_|$)", re.IGNORECASE),
    "currency_per_mass": re.compile(r"(?:^|_)(?:rub|currency)_per_(?:t|ton|tonne|mass)(?:_|$)", re.IGNORECASE),
    "mass_per_volume": re.compile(r"(?:^|_)(?:t|ton|tonne)_per_(?:m3|m³|volume)(?:_|$)", re.IGNORECASE),
    "well_count": re.compile(r"(?:^|_)(?:active_)?wells?(?:_count)?(?:_|$)|well_count", re.IGNORECASE),
    "step_count": re.compile(r"(?:^|_)(?:control_)?steps?(?:_count)?(?:_|$)|step_count", re.IGNORECASE),
    "iteration_count": re.compile(r"(?:^|_)iterations?(?:_count)?(?:_|$)", re.IGNORECASE),
    "record_count": re.compile(r"(?:^|_)records?(?:_count)?(?:_|$)", re.IGNORECASE),
    "edge_count": re.compile(r"(?:^|_)edges?(?:_count)?(?:_|$)", re.IGNORECASE),
    "duration_months": re.compile(r"(?:^|_)months?(?:_count)?(?:_|$)", re.IGNORECASE),
    "duration_years": re.compile(r"(?:^|_)years?(?:_count)?(?:_|$)", re.IGNORECASE),
    "coefficient": re.compile(r"(?:^|_)(?:coefficient|dimensionless|ood_score|weight)(?:_|$)", re.IGNORECASE),
    "percent": re.compile(r"(?:^|_)(?:watercut|percent|pct|ratio|fraction|share|proportion|compensation)(?:_|$)", re.IGNORECASE),
    "currency": re.compile(r"(?:^|_)(?:npv|rub|currency|cash|revenue|profit|economics|cost)(?:_|$)", re.IGNORECASE),
    "mass": re.compile(r"(?:^|_)(?:oil_)?mass(?:_|$)|\b(?:kg|kilograms?|кг|tonnes?|tons?|тонн\w*)\b", re.IGNORECASE),
    "volume": re.compile(r"(?:^|_)(?:injection_)?volume(?:_|$)|\b(?:m³|m3|м³|м3|bbl|barrels?)\b", re.IGNORECASE),
    "rate": re.compile(r"(?:^|_)rate(?:_|$)|flow|setpoint|oil_rate|liquid_rate|injection_rate|production_rate|(?:^|_)(?:production|injection)(?:_|$)|\b(?:m3|m³|м3|м³)\s*/\s*(?:day|сут(?:ки)?|день)\b|\b(?:t|т)\s*/\s*(?:day|сут(?:ки)?|день)\b", re.IGNORECASE),
    "pressure": re.compile(r"(?:^|_)(?:bhp|pressure|bar)(?:_|$)", re.IGNORECASE),
    "count": re.compile(r"count|iteration|control_step|step_count|active_wells|well_count|record_count|edge_count|depth", re.IGNORECASE),
}
_CLAIM_UNIT_PATTERNS = {
    "currency_per_volume": re.compile(r"(?:₽|руб\w*|rub(?:les?)?)\s*/\s*(?:m3|m³|м3|м³|cubic\s+met(?:er|re)s?)|\b(?:rub|currency)\s+per\s+(?:m3|m³|м3|м³|cubic\s+met(?:er|re)s?)", re.IGNORECASE),
    "currency_per_mass": re.compile(r"(?:₽|руб\w*|rub(?:les?)?)\s*/\s*(?:t|т|ton(?:ne|ne)?s?)|\b(?:rub|currency)\s+per\s+(?:t|т|ton(?:ne|ne)?s?)", re.IGNORECASE),
    "mass_per_volume": re.compile(r"(?:t|т|ton(?:ne|ne)?s?)\s*/\s*(?:m3|m³|м3|м³|cubic\s+met(?:er|re)s?)", re.IGNORECASE),
    "percent": re.compile(r"%|\bpercent\w*\b|\bпроцент\w*\b|\bfraction\b|\bдоля\b", re.IGNORECASE),
    "currency": re.compile(r"₽|\brub(?:les?)?\b|\bруб\w*\b|\$|\busd\b|\bdollars?\b", re.IGNORECASE),
    "rate": re.compile(r"\b(?:m³|m3|м³|м3)\s*/\s*(?:day|сут(?:ки)?|день)\b", re.IGNORECASE),
    "pressure": re.compile(r"\b(?:bar|bars|бар|mpa|мпа|kpa|кпа)\b", re.IGNORECASE),
    "well_count": re.compile(r"\b(?:wells?|скважин\w*)\b", re.IGNORECASE),
    "step_count": re.compile(r"\b(?:steps?|шаг\w*)\b", re.IGNORECASE),
    "iteration_count": re.compile(r"\biterations?|итерац\w*\b", re.IGNORECASE),
    "record_count": re.compile(r"\brecords?\b|\bзапис\w*\b", re.IGNORECASE),
    "edge_count": re.compile(r"\bedges?\b|\bсвязей\b", re.IGNORECASE),
    "duration_months": re.compile(r"\bmonths?\b|\bмесяц\w*\b", re.IGNORECASE),
    "duration_years": re.compile(r"\byears?\b|\bлет\b|\bгод\w*\b", re.IGNORECASE),
    "coefficient": re.compile(r"\bcoefficients?\b|\bкоэффициент\w*\b|\bweights?\b|\bвес\w*\b|\bscore\b|\bоод\b", re.IGNORECASE),
    "count": re.compile(r"\bcount\b|\bколичеств\w*\b", re.IGNORECASE),
}
_METRIC_PATTERNS = {
    "verified_npv": re.compile(r"verified[_ ]npv|подтвержд[её]нн\w*\s+чдд", re.IGNORECASE),
    "predicted_npv": re.compile(r"predicted[_ ]npv|прогноз\w*\s+чдд", re.IGNORECASE),
    "oil_rate": re.compile(
        r"oil[_ ]rate|oil\s+production(?:\s+rate)?|rate\s+of\s+oil\s+production|"
        r"дебит\w*\s+нефти|нефтян\w*\s+дебит|добыч\w*\s+нефти|нефт\w*\s+добыч\w*",
        re.IGNORECASE,
    ),
    "injection_rate": re.compile(r"injection[_ ]rate|дебит\w*\s+закачк\w*|закачк\w*\s+дебит", re.IGNORECASE),
    "liquid_rate": re.compile(r"liquid[_ ]rate|дебит\w*\s+жидкост\w*", re.IGNORECASE),
    "oil_mass": re.compile(r"oil[_ ]mass|масса\s+нефти|нефт\w*\s+масса", re.IGNORECASE),
    "injection_volume": re.compile(r"injection[_ ]volume|объ[её]м\w*\s+закачк\w*|закачк\w*\s+объ[её]м", re.IGNORECASE),
    "watercut": re.compile(r"watercut|обводн[её]нност\w*", re.IGNORECASE),
    "field_production": re.compile(r"\bproduction\b|\bliquid production\b|добыча\s+жидкости", re.IGNORECASE),
    "field_injection": re.compile(r"\binjection\b|закачк\w*", re.IGNORECASE),
    "compensation": re.compile(r"\bcompensation\b|компенсац\w*", re.IGNORECASE),
    "active_wells": re.compile(r"active[_ ]wells?|active well stock|действующ\w* фонд|число скважин", re.IGNORECASE),
    "pressure": re.compile(r"(?:\b(?:bottomhole\s+pressure|pressure|забойное\s+давление|давление\s+забоя)\b|(?:^|_)bhp(?:_|$))", re.IGNORECASE),
    "setpoint": re.compile(r"\bsetpoint\b|уставк\w*", re.IGNORECASE),
    "connectivity_weight": re.compile(r"\b(?:direct\s+)?(?:link|connectivity|connection)\s+weight\b|\bвес\w*\s+(?:прям\w*\s+)?связ\w*|\bweight\s+(?:of\s+(?:the\s+)?)?(?:direct\s+)?(?:link|connection)\b", re.IGNORECASE),
    "ood_score": re.compile(r"\bood(?:[_ ]score)?\b|\bout[- ]of[- ]distribution\s+score\b|\bоод\b", re.IGNORECASE),
    "npv_cumulative": re.compile(
        r"cumulative[_ ]npv|npv[_ ]cumulative|накопленн\w*\s+(?:чдд|npv)",
        re.IGNORECASE,
    ),
    "npv": re.compile(r"\bnpv\b|_npv(?:_|$)|\bчдд\b", re.IGNORECASE),
}
_METRIC_UNITS = {
    "verified_npv": "currency",
    "predicted_npv": "currency",
    "oil_rate": "rate",
    "injection_rate": "rate",
    "liquid_rate": "rate",
    "oil_mass": "mass",
    "injection_volume": "volume",
    "watercut": "percent",
    "field_production": "rate",
    "field_injection": "rate",
    "compensation": "percent",
    "active_wells": "well_count",
    "pressure": "pressure",
    "setpoint": "rate",
    "connectivity_weight": "coefficient",
    "ood_score": "coefficient",
    "npv_cumulative": "currency",
    "npv": "currency",
}
_METRIC_SENTENCE_BOUNDARY = re.compile(r"[;!?]|\.(?!\d)|\n")
_UNIT_TAGS = {
    "m3/day": "rate",
    "m³/day": "rate",
    "м3/сут": "rate",
    "м³/сут": "rate",
    "t/day": "rate",
    "т/сут": "rate",
    "rub/m3": "currency_per_volume",
    "rub/m³": "currency_per_volume",
    "руб/м3": "currency_per_volume",
    "руб/м³": "currency_per_volume",
    "rub/t": "currency_per_mass",
    "руб/т": "currency_per_mass",
    "t/m3": "mass_per_volume",
    "t/m³": "mass_per_volume",
    "т/м3": "mass_per_volume",
    "т/м³": "mass_per_volume",
    "rub": "currency",
    "rubles": "currency",
    "₽": "currency",
    "usd": "currency",
    "$": "currency",
    "kg": "mass",
    "кг": "mass",
    "m3": "volume",
    "m³": "volume",
    "м3": "volume",
    "м³": "volume",
    "bar": "pressure",
    "bars": "pressure",
    "бар": "pressure",
    "fraction": "percent",
    "percent": "percent",
    "%": "percent",
    "coefficient": "coefficient",
    "dimensionless": "coefficient",
    "well": "well_count",
    "wells": "well_count",
    "скважин": "well_count",
    "step": "step_count",
    "steps": "step_count",
    "шаг": "step_count",
    "шагов": "step_count",
    "iteration": "iteration_count",
    "iterations": "iteration_count",
    "итерация": "iteration_count",
    "итераций": "iteration_count",
    "record": "record_count",
    "records": "record_count",
    "запись": "record_count",
    "записей": "record_count",
    "edge": "edge_count",
    "edges": "edge_count",
    "связь": "edge_count",
    "связей": "edge_count",
    "month": "duration_months",
    "months": "duration_months",
    "месяц": "duration_months",
    "месяцев": "duration_months",
    "year": "duration_years",
    "years": "duration_years",
    "год": "duration_years",
    "лет": "duration_years",
}


@dataclass(frozen=True, slots=True)
class GuardResult:
    text: str
    ok: bool
    dropped: tuple[str, ...]

    @property
    def guarded(self) -> bool:
        return True


def guard_tool_failure_claims(
    text: str, cards: Sequence[Any], lang: str = "en"
) -> GuardResult:
    """Remove success claims for failed tools, preserving unrelated successful facts."""
    error_payloads = [
        (
            card.get("payload", {})
            if isinstance(card, Mapping)
            else getattr(card, "payload", {})
        )
        for card in cards
        if (
            card.get("type") if isinstance(card, Mapping) else getattr(card, "type", None)
        )
        == "error"
    ]
    if not cards or not error_payloads:
        return GuardResult(text=text.strip(), ok=True, dropped=())

    all_failed = len(error_payloads) == len(cards)
    failed_tools = {
        str(payload.get("tool", ""))
        for payload in error_payloads
        if isinstance(payload, Mapping)
    }

    kept: list[str] = []
    dropped: list[str] = []
    pending_separator = ""
    parts = re.split(r"(?<=[.!?])([ \t\r\n]+)", text.strip())
    for index in range(0, len(parts), 2):
        sentence = parts[index]
        separator = parts[index + 1] if index + 1 < len(parts) else ""
        affirmative = False
        for clause in DECISION_CLAUSE_BOUNDARY.split(sentence):
            if (
                not TOOL_SUCCESS_CLAIM.search(clause)
                or DECISION_CLAIM_NEGATION.search(clause)
            ):
                continue
            if all_failed or any(
                _tool_subject_pattern(tool).search(clause)
                for tool in failed_tools
                if tool
            ):
                affirmative = True
                break
        if affirmative:
            dropped.append(sentence)
            pending_separator = separator or pending_separator
        else:
            if kept and pending_separator:
                kept.append(pending_separator)
            kept.append(sentence)
            pending_separator = separator

    result = "".join(kept).strip()
    if not result and dropped:
        payload = error_payloads[0] if isinstance(error_payloads[0], Mapping) else {}
        reason = str(payload.get("message", "")).strip()
        next_step = str(payload.get("next_step", "")).strip()
        if lang == "ru":
            result = "Запрошенная операция не выполнена."
        else:
            result = "The requested operation was not completed."
        if reason:
            result += f" {reason}"
        if next_step:
            result += f" {next_step}"
    return GuardResult(text=result, ok=not dropped, dropped=tuple(dropped))


def _tool_subject_pattern(tool: str) -> re.Pattern[str]:
    pattern = TOOL_SUBJECT_PATTERNS.get(tool)
    if pattern is not None:
        return pattern
    escaped = re.escape(tool).replace(r"_", r"[_ -]")
    return re.compile(escaped, re.IGNORECASE)


def _known_run_ids(evidence: Sequence[Any]) -> set[str]:
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key) in _RUN_ID_FIELDS and isinstance(item, str):
                    cleaned = item.strip()
                    if cleaned and cleaned.casefold() not in {"unknown", "not recorded", "не записан"}:
                        found.add(cleaned)
                visit(item)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)

    for item in evidence:
        visit(item)
    return found


def guard_run_references(
    text: str, evidence: Sequence[Any], lang: str = "en"
) -> GuardResult:
    """Drop sentences that name a run identifier absent from current evidence."""
    known = _known_run_ids(evidence)
    kept: list[str] = []
    dropped: list[str] = []
    pending_separator = ""
    parts = re.split(r"(?<=[.!?])(\s+)", text.strip())
    for index in range(0, len(parts), 2):
        sentence = parts[index]
        separator = parts[index + 1] if index + 1 < len(parts) else ""
        references = _RUN_REFERENCE_PATTERN.findall(sentence)
        if any(reference not in known for reference in references):
            dropped.append(sentence)
            pending_separator = separator or pending_separator
        else:
            if kept and pending_separator:
                kept.append(pending_separator)
            kept.append(sentence)
            pending_separator = separator
    result = "".join(kept).strip()
    if not result and dropped:
        result = (
            "Идентификатор прогона не подтверждён карточками этого ответа."
            if lang == "ru"
            else "The run identifier is not confirmed by this answer's evidence cards."
        )
    return GuardResult(text=result, ok=not dropped, dropped=tuple(dropped))


def _reference_values(evidence: Sequence[Any], keys: frozenset[str]) -> set[str]:
    values: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key) in {"known_wells", "known_steps", "known_dates"} and isinstance(
                    item, (list, tuple, set)
                ):
                    values.update(
                        str(entry).strip().casefold()
                        for entry in item
                        if isinstance(entry, (str, int)) and not isinstance(entry, bool)
                    )
                if str(key) in keys and isinstance(item, (str, int)) and not isinstance(item, bool):
                    cleaned = str(item).strip()
                    if cleaned:
                        values.add(cleaned.casefold())
                visit(item)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)

    for item in evidence:
        visit(item)
    return values


def _date_keys(raw: str) -> set[str]:
    value = raw.strip()
    parsed: date | None = None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%d.%m.%Y").date()
        except ValueError:
            pass
    if parsed is not None:
        return {parsed.isoformat(), parsed.strftime("%Y-%m"), str(parsed.year)}

    year_match = re.search(r"\b((?:19|20)\d{2})\b", value)
    if year_match is None:
        return set()
    year = year_match.group(1)
    month_match = re.search(r"(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)", value, re.IGNORECASE)
    if month_match is None:
        return {year}
    month_name = month_match.group(1).casefold()
    aliases = (
        ("январ", "jan"), ("феврал", "feb"), ("март", "mar"),
        ("апрел", "apr"), ("ма", "may"), ("июн", "jun"),
        ("июл", "jul"), ("август", "aug"), ("сентябр", "sep"),
        ("октябр", "oct"), ("ноябр", "nov"), ("декабр", "dec"),
    )
    month = next(
        (index for index, names in enumerate(aliases, start=1) if any(month_name.startswith(name) for name in names)),
        None,
    )
    if month is None:
        return {year}
    return {f"{year}-{month:02d}"}


def _known_date_keys(evidence: Sequence[Any]) -> set[str]:
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key) in {
                    "date", "dates", "known_dates", "date_from", "date_to", "as_of",
                    "created_at", "updated_at", "timestamp",
                }:
                    candidates = item if isinstance(item, (list, tuple, set)) else (item,)
                    for candidate in candidates:
                        if isinstance(candidate, str):
                            found.update(_date_keys(candidate))
                visit(item)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)

    for item in evidence:
        visit(item)
    return found


def guard_context_references(
    text: str, evidence: Sequence[Any], lang: str = "en"
) -> GuardResult:
    """Drop prose that names a rule, well, or control step absent from current evidence."""
    known_rules = _reference_values(
        evidence, frozenset({"rule", "rule_id", "agent_id"})
    )
    known_wells = _reference_values(
        evidence, frozenset({"well", "selected_well", "known_wells", "a", "b"})
    )
    known_steps = _reference_values(
        evidence,
        frozenset({"step", "control_step", "from_step", "to_step", "known_steps"}),
    )
    known_dates = _known_date_keys(evidence)
    kept: list[str] = []
    dropped: list[str] = []
    pending_separator = ""
    parts = re.split(r"(?<=[.!?])([ \t\r\n]+)", text.strip())
    for index in range(0, len(parts), 2):
        sentence = parts[index]
        separator = parts[index + 1] if index + 1 < len(parts) else ""
        date_scan = _RUN_REFERENCE_PATTERN.sub(
            lambda match: "#" * len(match.group(0)), sentence
        )
        unsupported_date = bool(known_dates) and any(
            not (_date_keys(match.group(0)) & known_dates)
            for match in DATE_PATTERN.finditer(date_scan)
        )
        unsupported_rule = bool(known_rules) and any(
            match.group(0).casefold() not in known_rules
            for match in RULE_PATTERN.finditer(sentence)
        )
        unsupported_well = bool(known_wells) and any(
            match.group(1).casefold() not in known_wells
            for match in WELL_PATTERN.finditer(sentence)
        )
        unsupported_step = bool(known_steps) and any(
            match.group(1).casefold() not in known_steps
            for match in STEP_REFERENCE_PATTERN.finditer(sentence)
        )
        if unsupported_rule or unsupported_well or unsupported_step or unsupported_date:
            dropped.append(sentence)
            pending_separator = separator or pending_separator
        else:
            if kept and pending_separator:
                kept.append(pending_separator)
            kept.append(sentence)
            pending_separator = separator
    result = "".join(kept).strip()
    if not result and dropped:
        result = (
            "Правило, скважина, шаг или дата не подтверждены данными этого ответа."
            if lang == "ru"
            else "The rule, well, step, or date is not confirmed by this answer's evidence."
        )
    return GuardResult(text=result, ok=not dropped, dropped=tuple(dropped))


def _to_float(raw: str) -> float | None:
    cleaned = raw.replace("−", "-").replace(" ", "").replace(" ", "")
    cleaned = cleaned.replace(" ", "")
    if cleaned.count(",") == 1 and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def collect_numbers(value: Any, into: set[float] | None = None) -> set[float]:
    found = into if into is not None else set()
    if isinstance(value, bool):
        return found
    if isinstance(value, (int, float)):
        _add_variants(found, float(value))
        return found
    if isinstance(value, str):
        return found
    if isinstance(value, Mapping):
        for item in value.values():
            collect_numbers(item, found)
        return found
    if isinstance(value, (list, tuple, set)):
        for item in value:
            collect_numbers(item, found)
        return found
    return found


def _add_variants(into: set[float], value: float) -> None:
    into.add(value)
    into.add(value * 100.0)
    for scale in (1e-3, 1e-6, 1e-9):
        into.add(value * scale)


def _matches(candidate: float, allowed: Iterable[float]) -> bool:
    for value in allowed:
        if candidate == value:
            return True
        if _rounds_same(candidate, value):
            return True
    return False


def _field_unit(key: str) -> str | None:
    unit_tag = _UNIT_TAGS.get(key.strip().casefold().replace(" ", ""))
    if unit_tag is not None:
        return unit_tag
    if re.fullmatch(
        r"\s*(?:m3|m³|м3|м³)\s*/\s*(?:day|сут(?:ки)?|день)\s*",
        key,
        re.IGNORECASE,
    ):
        return "rate"
    if re.fullmatch(r"\s*(?:t|т)\s*/\s*(?:day|сут(?:ки)?|день)\s*", key, re.IGNORECASE):
        return "rate"
    for unit, pattern in _UNIT_FIELD_PATTERNS.items():
        if pattern.search(key):
            return unit
    return None


def _field_metric(key: str) -> str | None:
    if key.strip().casefold() == "weight":
        return "connectivity_weight"
    for metric, pattern in _METRIC_PATTERNS.items():
        if pattern.search(key):
            return metric
    return None


def _claim_metric(text: str, start: int, end: int, next_start: int) -> str | None:
    prefix = text[max(0, start - 100) : start]
    boundaries = list(_METRIC_SENTENCE_BOUNDARY.finditer(prefix))
    if boundaries:
        prefix = prefix[boundaries[-1].end() :]
    preceding = [
        (match.end(), metric)
        for metric, pattern in _METRIC_PATTERNS.items()
        for match in pattern.finditer(prefix)
    ]
    if preceding:
        return max(preceding, key=lambda item: item[0])[1]
    suffix = text[end : min(len(text), next_start, end + 48)]
    boundary = _METRIC_SENTENCE_BOUNDARY.search(suffix)
    if boundary is not None:
        suffix = suffix[: boundary.start()]
    following = [
        (match.start(), metric)
        for metric, pattern in _METRIC_PATTERNS.items()
        for match in pattern.finditer(suffix)
    ]
    if following:
        return min(following, key=lambda item: item[0])[1]
    return None


def _claim_unit(
    text: str, start: int, end: int, previous_end: int, next_start: int
) -> str | None:
    prefix = text[max(previous_end, start - 18) : start]
    suffix = text[end : min(next_start, end + 36)]
    context = prefix + suffix
    for unit, pattern in _CLAIM_UNIT_PATTERNS.items():
        if pattern.search(context):
            return unit
    return None


def _typed_numbers(
    value: Any,
    unit: str,
    into: set[float] | None = None,
    current_unit: str | None = None,
) -> set[float]:
    found = into if into is not None else set()
    if isinstance(value, bool):
        return found
    if isinstance(value, (int, float)):
        if current_unit != unit:
            return found
        number = float(value)
        found.add(number)
        if unit == "percent":
            found.add(number * 100.0)
        elif unit == "currency":
            found.update(number * scale for scale in (1e-3, 1e-6, 1e-9))
        return found
    if isinstance(value, Mapping):
        explicit_unit = value.get("unit", value.get("units"))
        explicit = _field_unit(str(explicit_unit)) if explicit_unit is not None else None
        for key, item in value.items():
            field_unit = _field_unit(str(key))
            if field_unit is not None and field_unit != unit:
                continue
            nested_unit = field_unit or explicit or current_unit
            _typed_numbers(item, unit, found, nested_unit)
        return found
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _typed_numbers(item, unit, found, current_unit)
    return found


def _metric_numbers(
    value: Any,
    metric: str,
    unit: str,
    into: set[float],
) -> None:
    if isinstance(value, Mapping):
        # Time-series and field-metric records carry the metric name as data
        # (`metric`/`id`) and the unit separately from the numeric value.
        # Bind the nested value to that declaration before walking the record.
        discriminator = value.get("metric", value.get("id"))
        declared_metric = _field_metric(str(discriminator)) if discriminator is not None else None
        if declared_metric is not None:
            matches_metric = declared_metric == metric or (
                metric == "npv" and declared_metric in {"verified_npv", "predicted_npv"}
            )
            declared_unit_value = value.get("unit", value.get("units"))
            declared_unit = (
                _field_unit(str(declared_unit_value))
                if declared_unit_value is not None
                else None
            )
            if matches_metric and declared_unit == unit:
                _typed_numbers(value, unit, into, declared_unit)
            return
        for key, item in value.items():
            field_metric = _field_metric(str(key))
            if field_metric is not None:
                if field_metric == metric or (metric == "npv" and field_metric in {"verified_npv", "predicted_npv"}):
                    field_unit = _field_unit(str(key))
                    if field_unit == unit:
                        _typed_numbers(item, unit, into, field_unit)
                continue
            _metric_numbers(item, metric, unit, into)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _metric_numbers(item, metric, unit, into)


def _round_significant(value: float, digits: int = SIGNIFICANT_DIGITS) -> float:
    if value == 0.0:
        return 0.0
    exponent = floor(log10(abs(value)))
    factor = 10 ** (digits - 1 - exponent)
    return round(value * factor) / factor


def _rounds_same(candidate: float, value: float) -> bool:
    if value == 0.0:
        return abs(candidate) < 1e-12
    if abs(candidate - value) <= abs(value) * RELATIVE_TOLERANCE:
        return True
    return _round_significant(candidate) == _round_significant(value)


def _masked(text: str) -> str:
    masked = DATE_PATTERN.sub(lambda match: "#" * len(match.group(0)), text)
    masked = RULE_PATTERN.sub(lambda match: "#" * len(match.group(0)), masked)
    return WELL_PATTERN.sub(lambda match: "#" * len(match.group(0)), masked)


def _formula_sources(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() == "formula" and isinstance(item, str) and item.strip():
                yield item.strip()
            yield from _formula_sources(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _formula_sources(item)


def _formula_signature(value: str) -> tuple[str, tuple[str, ...]]:
    cleaned = re.sub(r"^\s*>\s?", "", value.strip())
    cleaned = cleaned.strip("` ")
    numbers = tuple(match.group(0) for match in NUMBER_PATTERN.finditer(cleaned))
    structure = NUMBER_PATTERN.sub("#", cleaned)
    structure = re.sub(r"\s+", "", structure).casefold()
    return structure, numbers


def _grounded_formula_spans(text: str, evidence: Sequence[Any]) -> tuple[tuple[int, int], ...]:
    sources = {
        _formula_signature(source)
        for item in evidence
        for source in _formula_sources(item)
    }
    if not sources:
        return ()
    spans: list[tuple[int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        candidate = _formula_signature(line)
        if candidate in sources:
            spans.append((offset, offset + len(line)))
        offset += len(line)
    return tuple(spans)


def unsupported_numbers(
    text: str, allowed: Iterable[float], unit_evidence: Sequence[Any] = ()
) -> list[str]:
    allowed_values = list(allowed)
    masked = _masked(text)
    masked = _RUN_REFERENCE_PATTERN.sub(
        lambda match: "#" * len(match.group(0)), masked
    )
    formula_spans = _grounded_formula_spans(text, unit_evidence)
    unsupported: list[str] = []
    matches = list(NUMBER_PATTERN.finditer(masked))
    for index, match in enumerate(matches):
        if any(start <= match.start() < end for start, end in formula_spans):
            continue
        raw = text[match.start() : match.end()]
        value = _to_float(raw)
        if value is None:
            continue
        previous_end = matches[index - 1].end() if index > 0 else max(0, match.start() - 18)
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        unit = _claim_unit(text, match.start(), match.end(), previous_end, next_start)
        metric = _claim_metric(text, match.start(), match.end(), next_start)
        unit_values: set[float] = set()
        metric_values: set[float] = set()
        validation_unit = unit or _METRIC_UNITS.get(metric or "")
        if validation_unit is not None:
            for item in unit_evidence:
                _typed_numbers(item, validation_unit, unit_values)
                if metric is not None:
                    _metric_numbers(item, metric, validation_unit, metric_values)
        if not _matches(value, allowed_values) or (
            metric is not None
            and validation_unit is not None
            and not _matches(value, metric_values)
        ) or (
            validation_unit is not None
            and metric is None
            and not _matches(value, unit_values)
        ):
            unsupported.append(raw)
    return unsupported


def _strip(text: str, raw: str) -> str:
    stripped = text.replace(raw, "", 1)
    stripped = re.sub(r"\s{2,}", " ", stripped)
    stripped = re.sub(r"\s+([,.;:!?])", r"\1", stripped)
    return stripped.strip()


def allowed_numbers(
    tool_payloads: Sequence[Any], evidence: Sequence[Any] = ()
) -> set[float]:
    allowed: set[float] = set()
    for payload in tool_payloads:
        collect_numbers(payload, allowed)
    for document in evidence:
        collect_numbers(document, allowed)
    return allowed


def guard_caption(
    text: str, tool_payloads: Sequence[Any], evidence: Sequence[Any] = ()
) -> GuardResult:
    allowed = allowed_numbers(tool_payloads, evidence)
    unsupported = unsupported_numbers(text, allowed, (*tool_payloads, *evidence))
    if not unsupported:
        return GuardResult(text=text.strip(), ok=True, dropped=())
    cleaned = text
    for raw in unsupported:
        cleaned = _strip(cleaned, raw)
    return GuardResult(text=cleaned, ok=False, dropped=tuple(unsupported))


def normalize_code(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def code_blocks(text: str) -> list[str]:
    return [match.group(1) for match in FENCE_PATTERN.finditer(text)]


def strip_code(text: str) -> str:
    return FENCE_PATTERN.sub(" ", text)


@dataclass(frozen=True, slots=True)
class CodeResult:
    text: str
    ok: bool
    removed: tuple[str, ...]


def guard_code(text: str, sources: Sequence[str]) -> CodeResult:
    haystacks = [normalize_code(item) for item in sources if item]
    removed: list[str] = []
    cleaned = text
    for block in code_blocks(text):
        needle = normalize_code(block)
        if len(needle) < MIN_CODE_LENGTH:
            continue
        if any(needle in haystack for haystack in haystacks):
            continue
        removed.append(needle)
        match = FENCE_PATTERN.search(cleaned)
        while match is not None:
            if normalize_code(match.group(1)) == needle:
                cleaned = cleaned[: match.start()] + cleaned[match.end() :]
                break
            match = FENCE_PATTERN.search(cleaned, match.end())
    if not removed:
        return CodeResult(text=text, ok=True, removed=())
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return CodeResult(text=cleaned, ok=False, removed=tuple(removed))


def guard_answer(
    text: str,
    tool_payloads: Sequence[Any],
    evidence: Sequence[Any] = (),
    code_sources: Sequence[str] = (),
) -> tuple[GuardResult, CodeResult]:
    code = guard_code(text, code_sources)
    allowed = allowed_numbers(tool_payloads, evidence)
    segments = _outside_code(code.text)
    unsupported: list[str] = []
    for segment in segments:
        unsupported.extend(unsupported_numbers(segment, allowed, (*tool_payloads, *evidence)))
    if not unsupported:
        return GuardResult(text=code.text.strip(), ok=True, dropped=()), code
    cleaned = _replace_outside_code(code.text, unsupported)
    return (
        GuardResult(text=cleaned, ok=False, dropped=tuple(unsupported)),
        code,
    )


def guard_plan_status(text: str, tool_payloads: Sequence[Any], lang: str = "en") -> GuardResult:
    """Require a recorded acceptance verdict before claiming plan eligibility."""
    accepted = False
    rejected = False
    for payload in tool_payloads:
        if not isinstance(payload, Mapping):
            continue
        acceptance = payload.get("acceptance")
        if isinstance(acceptance, Mapping):
            verdict = acceptance.get("verdict")
            accepted |= verdict == "accepted_for_recorded_checks"
            rejected |= verdict == "rejected"
        plan_check = payload.get("plan_check")
        if isinstance(plan_check, Mapping):
            rejected |= plan_check.get("sound") is False
    ambiguous = accepted and rejected
    kept: list[str] = []
    dropped: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        positive_clause = any(
            POSITIVE_PLAN_STATUS.search(clause)
            and not PLAN_STATUS_NEGATION.search(clause)
            for clause in PLAN_STATUS_CLAUSE_BOUNDARY.split(sentence)
        )
        negative_clause = any(
            NEGATIVE_PLAN_STATUS.search(clause)
            for clause in PLAN_STATUS_CLAUSE_BOUNDARY.split(sentence)
        )
        if (positive_clause and (not accepted or ambiguous)) or (
            negative_clause and (not rejected or ambiguous)
        ):
            dropped.append(sentence)
        else:
            kept.append(sentence)
    if not dropped:
        return GuardResult(text=text.strip(), ok=True, dropped=())
    result = " ".join(kept).strip()
    if not result and dropped:
        if rejected and not ambiguous:
            result = (
                "План не прошёл проверку допуска."
                if lang == "ru"
                else "The plan did not pass the eligibility check."
            )
        elif accepted and not ambiguous:
            result = (
                "План принят по записанным проверкам."
                if lang == "ru"
                else "The plan passed the recorded checks."
            )
        else:
            result = (
                "Допуск плана не подтверждён записанной проверкой."
                if lang == "ru"
                else "The plan's eligibility is not confirmed by a recorded check."
            )
    return GuardResult(text=result, ok=not dropped, dropped=tuple(dropped))


def guard_decision_claims(text: str, tool_payloads: Sequence[Any], lang: str = "en") -> GuardResult:
    """Keep unsupported causality and optimality claims out of recorded-decision prose."""
    recorded_decision = any(
        isinstance(payload, Mapping)
        and (
            payload.get("record_status") == "observation-and-evidence-recorded"
            or (
                isinstance(payload.get("decision_summary"), Mapping)
                and payload["decision_summary"].get("basis") == "recorded-events; no causal inference"
            )
            or (
                payload.get("source") == "trace.json"
                and isinstance(payload.get("facts"), list)
                and payload.get("why") is None
            )
        )
        for payload in tool_payloads
    )
    if not recorded_decision:
        return GuardResult(text=text.strip(), ok=True, dropped=())
    kept: list[str] = []
    dropped: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        clauses = DECISION_CLAUSE_BOUNDARY.split(sentence)
        unsupported = any(
            any(
                not _decision_claim_is_negated(clause, claim)
                for claim in UNSUPPORTED_DECISION_CLAIM.finditer(clause)
            )
            for clause in clauses
        )
        if unsupported:
            dropped.append(sentence)
        else:
            kept.append(sentence)
    result = " ".join(kept).strip()
    if not result and dropped:
        result = (
            "В журнале записаны наблюдения и команды, но причинная связь или оптимальность не установлена."
            if lang == "ru"
            else "The journal records observations and commands; it does not establish causality or optimality."
        )
    return GuardResult(text=result, ok=not dropped, dropped=tuple(dropped))


def _outside_code(text: str) -> list[str]:
    pieces: list[str] = []
    position = 0
    for match in FENCE_PATTERN.finditer(text):
        pieces.append(text[position : match.start()])
        position = match.end()
    pieces.append(text[position:])
    return pieces


def _replace_outside_code(text: str, unsupported: Sequence[str]) -> str:
    pieces: list[str] = []
    position = 0
    remaining = list(unsupported)
    for match in FENCE_PATTERN.finditer(text):
        pieces.append(_strip_all(text[position : match.start()], remaining))
        pieces.append(match.group(0))
        position = match.end()
    pieces.append(_strip_all(text[position:], remaining))
    return re.sub(r"\n{3,}", "\n\n", "".join(pieces)).strip()


def _strip_all(text: str, remaining: list[str]) -> str:
    cleaned = text
    for raw in list(remaining):
        if raw not in cleaned:
            continue
        cleaned = cleaned.replace(raw, "", 1)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"[ \t]+([,.;:!?])", r"\1", cleaned)
        remaining.remove(raw)
    return cleaned
