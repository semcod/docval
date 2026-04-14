# code2logic benchmark

Kompresja kontekstu przez AST + logikę funkcji (`code2logic`).

## Pliki w folderze

- [benchmark.py](./benchmark.py) — uruchomienie benchmarku
- [results.json](./results.json) — metryki benchmarku
- [llm/system.txt](./llm/system.txt) — system prompt
- [llm/input.txt](./llm/input.txt) — pełny prompt wysłany do LLM
- [llm/context.txt](./llm/context.txt) — kontekst wejściowy po kompresji
- [llm/output.txt](./llm/output.txt) — odpowiedź LLM
- [llm/metadata.json](./llm/metadata.json) — tokeny/czas/model/target
- [llm/timeline.log](./llm/timeline.log) — harmonogram wywołań LLM

## Jak odtworzyć artefakty

```bash
make benchmark-code2logic
```

Po uruchomieniu benchmarku pliki w `llm/` są nadpisywane najnowszym przebiegiem.
