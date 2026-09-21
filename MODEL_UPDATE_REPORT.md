# Итог доработки исследовательской модели

Изменения выполнены только в `E:\статья`.

- Полный pytest: **249 passed**, одно предупреждение устаревшего API Altair внутри Streamlit; ошибок нет.
- Технический эксперимент: **10/10**, все `validation_passed=true`.
- Streamlit: `/_stcore/health` → `ok`; главная страница → HTTP 200. Проверочный процесс остановлен после проверки; сценарии интерфейса дополнительно проверены AppTest.
- Расчётные модули constraints, scoring, sensitivity, explanation, factors, risks, uncertainty и p3_format побайтово совпадают с исходными (контроль SHA-256). В models.py изменён только загрузчик конфигурации; ExplanationData, валидация и формулы не изменены. P2 получил уточнение обязательного значения Да/Нет; содержание уровней P1/P2/P3 сохранено.
- Загрузчик разворачивает шесть общих правил рисков для A1/A2/A3 в прежний формат. Поэтому порог ≤ 2 работает также при изменённых estimated/missing-оценках кейса любой архитектуры.

## Итоговая матрица

| Критерий | A1 Монолит | A2 SOA | A3 Микросервисы |
| --- | --- | --- | --- |
| K1 Масштабируемость | 2 | 4 | 5 |
| K2 Независимость изменений и развёртывания | 1 | 4 | 5 |
| K3 Интеграционная гибкость | 2 | 5 | 4 |
| K4 Простота разработки | 5 | 3 | 2 |
| K5 Простота эксплуатации | 5 | 3 | 2 |
| K6 Стоимость / экономичность | 4 | 3 | 2 |

Все направления — maximize, читаются из конфигурации. Шкала порядковая: 1 — выраженно неблагоприятное положение, 2 — неблагоприятное, 3 — промежуточное/смешанное, 4 — преимущество, 5 — выраженное преимущество. Числа не являются нормативными значениями из литературы; K6 не является расчётом TCO.

## Доступные обязательные ограничения

| Свойство | A1 | A2 | A3 |
| --- | --- | --- | --- |
| Независимое развёртывание компонентов | Нет | Да | Да |
| Единая развёртываемая единица | Да | Нет | Нет |

Для обоих доступны только «Равно» и «Да/Нет». «Нет» требует отсутствия свойства. Снять требование можно удалением строки. Оба «Да» исключают все альтернативы; ограничения не ослабляются.

## Полный список правил рисков

- **R1: K1 ≤ 2** — Ограниченная масштабируемость может затруднить адаптацию системы к существенному росту нагрузки.
- **R2: K2 ≤ 2** — Ограниченная независимость изменений и развёртывания повышает связанность изменений между компонентами системы.
- **R3: K3 ≤ 2** — Ограниченная интеграционная гибкость может усложнить взаимодействие с разнородными системами и сервисами.
- **R4: K4 ≤ 2** — Архитектурный вариант предъявляет повышенные требования к сложности разработки и координации компонентов.
- **R5: K5 ≤ 2** — Архитектурный вариант связан с повышенной сложностью эксплуатации, наблюдаемости и сопровождения распределённых компонентов.
- **R6: K6 ≤ 2** — В рамках модельной постановки архитектурный вариант связан с повышенными инфраструктурными и эксплуатационными накладными расходами.

## Результаты и изменённые файлы

- [app.py](<app.py>)
- [README.md](<README.md>)
- [config/architectures.json](<config/architectures.json>)
- [config/criteria.json](<config/criteria.json>)
- [config/constraints.json](<config/constraints.json>)
- [config/risks.json](<config/risks.json>)
- [data/example_cases.json](<data/example_cases.json>)
- [data/experiment_results.csv](<data/experiment_results.csv>)
- [data/experiment_results.json](<data/experiment_results.json>)
- [data/experiment_results_config_snapshot.json](<data/experiment_results_config_snapshot.json>)
- [src/models.py](<src/models.py>)
- [src/user_cases.py](<src/user_cases.py>)
- [src/p2_format.py](<src/p2_format.py>)
- [src/experiment.py](<src/experiment.py>)
- [tests/test_constraints.py](<tests/test_constraints.py>)
- [tests/test_factors.py](<tests/test_factors.py>)
- [tests/test_p2_format.py](<tests/test_p2_format.py>)
- [tests/test_user_cases.py](<tests/test_user_cases.py>)
- [tests/test_final_configuration.py](<tests/test_final_configuration.py>)

Новый CSV и снимок находятся в `data/`; результаты в `work/experiment_results.*` относятся к прежнему запуску и не используются. Дополнительно создан этот отчёт `MODEL_UPDATE_REPORT.md` и служебные файлы проверки в `work/`: журналы `pytest-final-model-*.log`, тестовые каталоги `pytest-final-model-*`, `core_hashes.json`, `streamlit-final-check.json`, журналы `streamlit-final.*.log`, `legacy-paths.txt`, `legacy-audit.json`, скрипт проверки запуска `verify_startup.py`. Временные скрипты изменения исходников удалены. Устаревшие `src/__pycache__` и `tests/__pycache__` удалены.

## Поиск старых свойств

Поиск rg выполнен по исходникам, конфигурации, тестам, данным и историческим рабочим копиям, включая скрытые файлы. Установленные зависимости `.venv`, `.python`, `.uv-cache` и Git-метаданные исключены; ZIP проверен отдельно без распаковки. Каталог `.pytest_cache` недоступен для перечисления из-за прав ОС, поэтому полную проверку его содержимого подтвердить нельзя.

В действующих `app.py`, `README.md`, `src/`, `tests/`, `config/`, `data/` старые строки **не найдены**. Ни выпадающий список, ни формирование пользовательских требований не предлагают старые свойства. Исторические копии и ZIP сохранены; они не подключаются приложением. Ниже указан полный список найденных мест. Сами поисковые термины в этом отчёте и `work/legacy-audit.json` являются только документированием проверки.

### `operating_units`

- `work\experiment_results.json`
- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_experiment_writes_csv_and0\experiment.json`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\config\architectures.json`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\tests\test_user_cases.py`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\config\constraints.json`
- `architecture-prototype.zip :: config/architectures.json`
- `architecture-prototype.zip :: config/constraints.json`
- `architecture-prototype.zip :: tests/test_user_cases.py`

### `integration_capacity`

- `work\experiment_results.json`
- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_experiment_writes_csv_and0\experiment.json`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\config\architectures.json`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\tests\test_user_cases.py`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\config\constraints.json`
- `architecture-prototype.zip :: config/architectures.json`
- `architecture-prototype.zip :: config/constraints.json`
- `architecture-prototype.zip :: tests/test_user_cases.py`

### `deployment_mode`

- `work\experiment_results.json`
- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_user_model_loads_architec0\config\architectures.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_experiment_writes_csv_and0\experiment.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_experiment_writes_csv_and0\experiment.json`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\config\architectures.json`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\tests\test_user_cases.py`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\config\constraints.json`
- `architecture-prototype.zip :: config/architectures.json`
- `architecture-prototype.zip :: config/constraints.json`
- `architecture-prototype.zip :: tests/test_user_cases.py`

### `Число эксплуатационных единиц`

- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_user_model_loads_architec0\config\constraints.json`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\config\constraints.json`
- `architecture-prototype.zip :: config/constraints.json`

### `Интеграционная ёмкость`

- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_user_model_loads_architec0\config\constraints.json`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\config\constraints.json`
- `architecture-prototype.zip :: config/constraints.json`

### `Способ развёртывания`

- `work\pytest-ffc42724bfe4410db1c4c2e66e4f532f\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-03aa39bb3b1e45388ab35abdd58785b8\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-7eebe5d096534c4ba043d1a19523fc25\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-dc41ee0bf7694827ab7ad7805972b3ea\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-e6dac31d8423472e862b93a37d993fb0\test_user_model_loads_architec0\config\constraints.json`
- `work\pytest-b5abc15eb76149488d07af64fa252172\test_user_model_loads_architec0\config\constraints.json`
- `work\transfer-ec62df1f3f87469db7e7bc987cabff1b\config\constraints.json`
- `architecture-prototype.zip :: config/constraints.json`
