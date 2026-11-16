# Chapter 11 - retrieval-augmented generation

```bash
cd code/rag
python eval_recall.py --config all
```

```
dense_only               recall@20 0.575   recall@5 0.200
hybrid                   recall@20 0.700   recall@5 0.200
hybrid_contextual        recall@20 1.000   recall@5 0.950
hybrid_contextual_rerank recall@20 1.000   recall@5 0.975
```

The corpus is synthetic but built to reproduce the real failure: every chunk
says "the company" without naming it, so a dense retriever cannot answer
"what was ACME's Q2 2023 revenue growth". Contextualisation prepends the
document identity before indexing, and the recall number moves.

- `corpus.py` - 8 filings x 4 quarters x 5 topics, plus two question families.
- `retrieve.py` - BM25, a trigram-hash dense proxy, and reciprocal rank fusion.
- `rerank.py` - cross-encoder stub over the shortlist, batched.
- `eval_recall.py` - recall@20 and recall@5 per configuration.
