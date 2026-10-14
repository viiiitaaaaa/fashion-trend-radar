# ТЗ: система скоринга трендов (вместо «один сигнал → сразу товар»)

Заменяет прежнюю логику «нашли тренд в Google Trends → сразу ищем товар на AliExpress».
Каждую неделю собираем 20–30 кандидатов, оставляем 3–5 с несколькими независимыми сигналами.

## Источники сигналов

| Источник | Статус в проекте | Метрика |
|---|---|---|
| Google Trends | ✅ уже собирается (`run.py`, Bright Data) | Динамика 90 дней / 12 мес., rising queries, география |
| Pinterest | ✅ уже собирается | Weekly/monthly/yearly change, повторяемость визуала |
| TikTok | ✅ уже собирается | Число независимых роликов/авторов, purchase-intent в комментариях |
| Instagram | ✅ уже собирается | Reels, saveability |
| TikTok Creative Center | ⏳ не реализовано | Трендовые хэштеги/креативы по стране |
| Meta Ad Library | ⏳ не реализовано | Длина жизни активной рекламы у конкурентов |
| Amazon Best Sellers / Movers & Shakers | ⏳ не реализовано | Коммерческое подтверждение спроса |
| Google Merchant Center Popular Products | ⏳ не реализовано | rank / previous rank / изменение спроса |
| Etsy, Depop | ⏳ не реализовано | Микрониши, эстетики |
| Alibaba/1688/CJ/Zendrop | ⏳ не реализовано (заменяет AliExpress) | Поставщик, MOQ, кастомизация — **только после** подтверждения тренда, не как источник идей |

## Формула Trend Score

```
Trend Score = 0.20·G + 0.20·P + 0.20·T + 0.15·C + 0.15·M + 0.10·U − S − H
```

- G — Google спрос и ускорение (0–5)
- P — Pinterest визуальный спрос (0–5)
- T — TikTok повторяемость + purchase-intent в комментариях (0–5)
- C — коммерческое подтверждение (маркетплейсы/ритейл) (0–5)
- M — маржа и доступность поставщика (0–5)
- U — уникальность / потенциал контента (0–5)
- S — штраф за сезонность (0–5)
- H — штраф за насыщение одинаковыми дропшиппинг-листингами (0–5)

Порог отбора: **≥ 3.5/5**, без сильного штрафа за насыщение (H).

## Проверка «сигнал, а не шум» (нужно 4 из 6)

1. Google: рост за 90 дней, не только сезонный повтор
2. Pinterest: растущий визуальный интерес + повторяющийся силуэт/материал/стиль
3. TikTok: ≥5 независимых авторов за 30 дней
4. Purchase intent: в комментариях просят ссылку/название/цену
5. Коммерческая валидация: похожие модели заметны на Amazon/Etsy/Google Shopping/ритейле
6. Контент: можно снять ≥20 роликов без повторов

## Порядок работы (новый, без AliExpress на старте)

1. Google Trends → растущий keyword/topic
2. Pinterest Trends → не сезонный ли всплеск, какие визуальные варианты растут
3. TikTok → 5–15 роликов, хуки, purchase-intent в комментариях
4. Instagram → можно ли сделать сохраняемый контент
5. Amazon / Google Shopping / Etsy / ритейл → подтверждение покупательского спроса
6. Alibaba/1688/AliExpress/CJ → **только теперь** ищем поставщика и версию лучше конкурентов
7. Контент-тест → сэмпл + Reels/TikTok до закупки

## Код (актуальная реализация, 21.09.2026)

| Файл | Что делает | Статус |
|---|---|---|
| `src/processors/fashion_score.py` | `FashionCandidate`, `google/pinterest/tiktok/commercial/uniqueness/margin_score`, `calculate_fashion_score(c, seasonality_penalty, saturation_penalty)` | ✅ работает |
| `src/processors/seasonality.py` | `detect_seasonality()` — штраф 0–15, отдельно от score, нужно ≥80 недель истории | ✅ работает, сейчас всегда `NOT_ENOUGH_HISTORY` (есть только 53 недели) |
| `src/processors/saturation.py` | `calculate_saturation_penalty()` — штраф 0–15 по дублям/Meta Ads/поставщикам | ✅ работает, сейчас всегда `LOW_SATURATION` (входные поля не собираются) |
| `src/processors/market_concentration.py` | HHI, CR3/CR5, Clone Saturation Index, price CV, Market Entry Risk | ✅ код готов, нужны данные по продавцам/ценам — не собираются |
| `src/collectors/google_trends_pytrends.py` | 2-летняя история по одному keyword через pytrends, простой вариант | ✅ код готов, **не запускался** |
| `src/collectors/google_trends_safe.py` | То же самое, но с кэшем на диске, backoff+jitter при ошибках, не долбит при 429 | ✅ код готов, **не запускался** — предпочтительнее простого варианта выше |
| `src/processors/seasonality_analysis.py` | Расширенная сезонность: `seasonal_index` по неделям года, `seasonality_strength`, `peak_week` | ✅ код готов, не подключён к `run_fashion_score.py` (тот использует более лёгкий `seasonality.py`) |
| `src/processors/market_concentration.py` | + `calculate_market_concentration()` (HHI+C4+CR8+effective_competitors, регистронезависимые продавцы) | ✅ добавлено поверх старых `calculate_hhi`/`concentration_ratio` |
| `src/processors/normalization.py` | Единая схема событий (`CANONICAL_COLUMNS`) + адаптеры TikTok/Amazon/Google Trends + `aggregate_tiktok_daily` | ✅ код готов, не подключён — сейчас `run_fashion_score.py` читает CSV напрямую, без единой схемы |
| `run_fashion_score.py` | Собирает всё вместе на текущих данных, пишет `data/reports/fashion_score.csv` | ✅ работает |

**Решение, которое пока не принято:** `seasonality.py` (лёгкий, уже подключён) vs `seasonality_analysis.py` (богаче, даёт недельный сезонный индекс) — держать оба смысла нет, при следующем реальном использовании сезонности выбрать один и убрать дубль.

## Пять независимых модулей (21.09.2026, второй раунд)

Специально НЕ объединены в один парсер — каждый работает сам по себе поверх стабильной таблицы данных.

| Модуль | Что делает | Нужны реальные данные? |
|---|---|---|
| `src/collectors/google_trends_safe.py` | Безопасный сбор Google Trends: кэш, backoff, отдельная длинная пауза именно на 429 (не обход, а пауза) | Готов к запуску, не запускался |
| `src/processors/fashion_taxonomy.py` | Раскладывает keyword на Category/Silhouette/Material/Detail/Audience — проверено на 3 примерах, работает | Нет — работает уже сейчас на любых keyword |
| `src/processors/unit_economics.py` | `calculate_cac`, `calculate_customer_ltv` (contribution LTV) | Нужны реальные заказы Shopify — сейчас бесполезен без них |
| `src/collectors/marketplace_provider.py` | Provider-agnostic архитектура для WB/Ozon/Amazon — **без скрейпера чужой выдачи**, только через официальный API/разрешённого провайдера | Нужен авторизованный provider — не подключён |
| `src/processors/cohort_analysis.py` | Retention cohorts, LTV cohorts, refund rate по сегменту | Нужны реальные заказы Shopify — сейчас бесполезен без них |

**Порядок включения (из твоего сообщения):** Google Trends history → fashion taxonomy → market concentration (уже есть) → marketplace dataset → cohorts/LTV/CAC (как только появятся первые заказы).

## Консолидация (21.09.2026, третий раунд)

Ты прислала финальные, более отточенные версии тех же модулей — свела дубли, а не плодила новые файлы:

- **Google Trends сборщик:** было 2 черновика (CSV-кэш) → удалены, остался один канонический `src/collectors/google_trends_cached.py` — Parquet-кэш, TTL по размеру окна, backoff с увеличенным множителем именно на 429, `merge_google_trends_history()` для склейки 730d+90d снимков
- **`unit_economics.py`:** добавлены `prepare_order_economics()` (полная модель costs: скидки, ad_spend, creator_cost), `calculate_cac_batch()`, `calculate_customer_ltv_from_prepared()` — поверх старых (те остаются для быстрого разового расчёта без полной модели). Проверено на синтетических данных — работает.
- **`cohort_analysis.py`:** добавлены `add_cohort_fields()`, `build_retention_matrix()`, `build_cohort_ltv_matrix()` — версия ближе к тому, как считает сам Shopify (retention = active/cohort_size). Требует `prepare_order_economics()` перед `build_cohort_ltv_matrix()`.
- **`seasonality_analysis.py`:** добавлена `decompose_fashion_seasonality()` — сезонно-скорректированный momentum (`seasonally_adjusted_momentum_pct`), дополняет уже бывший в файле `analyze_seasonality()`.

**Дубли, которые всё ещё остались и требуют решения при первом реальном использовании:** `seasonality.py` (лёгкий, подключён к `run_fashion_score.py`) vs `seasonality_analysis.py` (богатый, не подключён) — выбрать один при переходе на 2-летнюю историю.

**Важно:** штрафы (seasonality/saturation) считаются один раз снаружи и передаются в `calculate_fashion_score` готовыми числами — раньше была двойная логика, могли вычитаться дважды, это исправлено.

## Этапы внедрения

- [x] Убрать прежнюю логику «тренд → сразу AliExpress-товар» (21.09.2026)
- [x] **Шаг 1:** Trend Score по уже собираемым источникам (G/P/T), раздельные штрафы сезонности и сатурации — `run_fashion_score.py`
- [ ] Шаг 1.5: запустить `google_trends_pytrends.py` на 2 года — накопить историю, чтобы `detect_seasonality` заработал по-настоящему (нужно подтверждение — живой сетевой сбор)
- [ ] Шаг 2: Amazon Best Sellers / Movers & Shakers → `commercial_score`
- [ ] Шаг 3: Meta Ad Library → `commercial_score` + `saturation_penalty`
- [ ] Шаг 4: TikTok Creative Center (ранние контент-сигналы)
- [ ] Шаг 5: Etsy/Depop для микрониш
- [ ] Шаг 6: продавцы/цены/дубли листингов (Amazon/Google Shopping/AliExpress) → `market_concentration.py` заработает
- [ ] Шаг 7: официальный Pinterest API v5 (сейчас скрейп пинов, weekly/monthly growth нет — `pinterest_score` почти пустой)
- [ ] Шаг 8: подключить поставщиков (Alibaba/1688/CJ/Zendrop) — только на входе кандидата, прошедшего скоринг

## Правила радара на 2 годах (22.09.2026)

`src/processors/candidate_matrix.py`, `window_stats()` / `is_seasonal()`:
- Google (2 года по всем кандидатам) и Pinterest (2 года, сырые недели из `data/raw/pinterest_trends/metrics_*.json`) сравниваются **по периоду**: среднее за последние 8 недель против тех же 8 недель год назад. Одна «выстрелившая» неделя больше не решает.
- Проверка засчитывается при росте **≥ +15%** (одинаково для Google и Pinterest; +1–3% — шум).
- **Сезон** = год назад в эти же недели интерес тоже поднялся на ≥20% относительно 8 недель до них, а в этом году рост к прошлому году < 15%. Сначала по Pinterest, если нет — по Google.
- Однонедельный yoy Pinterest оставлен в колонке `pin_yoy_1w_pct` для сравнения.
- **YouTube** (6-й канал, 22.09): поиск на YouTube за 2 года через Google Trends (`gprop="youtube"`), `run_trends_bootstrap.py --youtube`, данные в `data/normalized/google_trends_youtube`. Та же проверка: 8 недель к прошлому году ≥ +15%. Решение теперь «из 6»: ≥4 TEST, 3 WATCH.
- **YouTube Data API** (`run_youtube_api.py`, ключ `YOUTUBE_API_KEY` в `.env`, ~220 единиц квоты на кандидата из 10 000/день): видео за 90 дней против тех же 90 дней год назад (США, каналы из IN/PK/BD/NP/LK отброшены — иначе шум от Myntra/Flipkart-хаулов), просмотры, комментарии «где купить / link / хочу». Галочка Y = кривая поиска ≥ +15% ИЛИ просмотры свежих видео ≥ +15% к прошлому году (прошлогодние видео копили просмотры на год дольше — оценка осторожная). Комментарии «где купить» пока только показываются, в решение не входят. Собрано 22.09 для 3 лидеров.
- **Длина сезона ≥ 2 месяцев** (правило пользователя, 22.09): сезонные вещи рассматриваем, но спрос должен держаться не меньше 8 недель. `season_weeks()`: 2 года по неделям (сначала Pinterest, иначе Google), сглаживание 3 недели, вокруг пика каждого года считаем недели подряд не ниже половины пика, берём самый длинный сезон. Ряд меряется целиком, без разреза по годам — осенние сезоны начинаются в сентябре, ровно на стыке. Если все сезоны упираются в край данных (ещё идут), короткое число не считается приговором. Короче 8 недель → REJECT «короткий сезон», сколько бы каналов ни подтверждали. На 22.09 так отсекается только hoco dress (6 недель, событие homecoming).
- **Только стабильно растущие** (правило пользователя, 22.09): вещь проходит, только если по Pinterest последние 8 недель И минимум 3 из 4 последних кварталов выше тех же периодов прошлого года на 15%+ (`quarterly_growth()`, `is_stable_growth()`). Нет Pinterest-кривой → «рост не проверить» → отказ. Сезонные «хиты без роста» (faux fur coat, cable knit) отдельной группой НЕ заводим — пользователь отказалась.
- **Сбой в Google Trends весной 2026:** у 13 из 19 слов пик за 2 года — апрель 2026 (свитера, осенние куртки, кардиганы), медиана всех слов в апреле = 100% от своего максимума. Это артефакт данных, а не спрос: он раздувает рост Google на длинных окнах (кварталы, год) в сотни и тысячи процентов. Поэтому стабильный рост меряем только по Pinterest; Google-проверка 8 недель (июль–сентябрь) сбоем не задета. Так funnel neck sweater выглядел «растущим», хотя по сентябрям 30 → 28 → 35.
- **Редкие кривые не считаются** (`MIN_NONZERO = 0.5`): если меньше чем в половине недель есть данные, фраза ищется слишком редко и «рост» 0→12 — шум. На графике такие кривые подписаны «мало поисков — не учитываем». У YouTube достаточно данных пока только у 4 кандидатов из 22.
- Дашборд: `build_dashboard.py` → `data/reports/trend_radar_dashboard.html` + блок кривых (`radar_curves.py`) вверху `dolphin_anty/trend_radar_dashboard.html`.

## Отложено до этапа контент-теста (шаг 7)

**TikTok Symphony API 2026** (ИИ-генерация рекламных роликов: Generate & Remix, Digital Avatar, Dubbing, Image to Video, Smart Fix, Creative Pre-review). Для поиска трендов не подходит, но нужен, когда радар выберет товар: быстро сделать 10–20 роликов без съёмки. Руками — Symphony Creative Studio (ads.tiktok.com/creative/creativestudio, вход через TikTok for Business). API — отдельная заявка/партнёрский доступ. Гайд: bytedance.larkoffice.com/wiki/KcOawZdBwiiI0MkTOU8c6a2Lnac (нужен вход в Lark).
