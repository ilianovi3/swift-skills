# Swift skills

Скиллы для агентов (Claude Code и совместимых) для нативной разработки на Swift: перенос веб-интерфейса в SwiftUI
один в один и оптимизация клиента до плавности системных приложений. Выросли из практики порта Next.js-прототипа
в macOS-приложение: каждое правило проверено замерами или попиксельным сравнением.

| Скилл | Что решает |
| --- | --- |
| [`react-to-swift`](react-to-swift/SKILL.md) | Переписать React / Next.js / Tailwind-компонент или экран в SwiftUI визуально 1:1, но с нативным устройством: структура под производительность, перевод CSS значение в значение, типографика как в браузере, проверка попиксельным сравнением. |
| [`optimize-swift`](optimize-swift/SKILL.md) | Максимально оптимизировать клиент, экран или компонент: замер на настоящем вводе пользователя, метрика «доля кадров на 120 Гц при движении», каталог корневых причин с подписями в трассах и нативные исправления, не меняющие вид. |

Скиллы дополняют общие `swiftui-performance`, `swift-performance-optimization`, `swiftui-pro`,
`swiftui-uikit-interop` и не повторяют их.

## Установка

```sh
git clone <этот репозиторий> ~/dev/skills-swift
ln -s ~/dev/skills-swift/react-to-swift ~/.claude/skills/react-to-swift
ln -s ~/dev/skills-swift/optimize-swift ~/.claude/skills/optimize-swift
```

После установки в Claude Code: `/reload-skills`.

## Устройство

```
react-to-swift/
  SKILL.md                     порядок работы и главные правила
  references/css-to-swiftui.md CSS и Tailwind → SwiftUI значение в значение
  references/typography.md     шрифты, оси, CSS line-height, трекинг, сглаживание, переносы
  references/parity-check.md   снимки без окон на экране, сравнение и измерение отступов
  scripts/window_shot.sh       снимок окна приложения (+ window_id.swift)
  scripts/pixdiff.py           разница двух снимков, рамки «чернил» для измерения сдвигов
  evals/evals.json             тестовые запросы
optimize-swift/
  SKILL.md                     принципы, порядок работы, таблица корневых причин
  references/root-causes.md    причины, как подтвердить, исправления, ловушки
  references/patterns.md       готовые паттерны кода (HostedStack, флаги наведения, абзац одним Text, …)
  references/measure.md        запись настоящей прокрутки, чтение трасс, эталон Safari, слепые пары
  scripts/analyze_trace.py     сводка трассы xctrace: кадры, 120 Гц при движении, главный поток по подписям
  scripts/trace_callers.py     кто вызывает подпись и на что она тратит время
  scripts/record_manual.sh     запись 20 с прокрутки пользователем с отсчётом на плашке
  scripts/record_reference.sh  эталонная запись Safari и других системных приложений
  scripts/cue.swift            плашка с отсчётом в углу экрана
  evals/evals.json             тестовые запросы
```

## Требования

macOS с Xcode (`xcrun xctrace`, `swiftc`), Python 3, для `pixdiff.py` — Pillow (`pip install pillow`), для снимков
веб-рефа — Playwright (`npx playwright`). Записи прокрутки и снимки окна на время занимают экран: агент должен
предупреждать пользователя.

## Как пополнять

Новая находка по производительности или по переносу с веба — строка в соответствующем `references/*.md` с цифрами
«было → стало» и способом подтверждения; отвергнутые опыты тоже записываются. `SKILL.md` держать коротким (< 500
строк): подробности — в `references/`.
