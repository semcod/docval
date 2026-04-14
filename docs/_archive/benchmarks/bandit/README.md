# bandit benchmark

Kompresja kontekstu przez analizę bezpieczeństwa (`bandit`).

## Pliki w folderze

- [benchmark.py](./benchmark.py) — uruchomienie benchmarku
- [results.json](./results.json) — metryki benchmarku
- [llm/system.txt](./llm/system.txt) — system prompt
- [llm/input.txt](./llm/input.txt) — prompt wysłany do LLM
- [llm/context.txt](./llm/context.txt) — kontekst wykrytych ryzyk bezpieczeństwa
- [llm/output.txt](./llm/output.txt) — odpowiedź LLM
- [llm/metadata.json](./llm/metadata.json) — tokeny/czas/model/target
- [llm/timeline.log](./llm/timeline.log) — harmonogram wywołań LLM

## Jak odtworzyć artefakty

```bash
make benchmark-bandit
```
