# Knowledge2 Python SDK

Official Python client for the Knowledge2 public API.

- Website: https://knowledge2.ai
- Support: contact@knowledge2.ai

## Install

This SDK is designed to be published directly from the `sdk/` directory. Once published, install it via pip using your package name.

## Quick start (end-to-end)

This example ingests a sizeable public dataset (Project Gutenberg), builds indexes, runs a tuning job, and then queries.

```python
from urllib.request import urlopen
from sdk import Knowledge2

client = Knowledge2(api_key="YOUR_API_KEY")
corpus = client.create_corpus(client.create_project("quickstart")["id"], "quickstart")
text = urlopen("https://www.gutenberg.org/files/11/11-0.txt").read().decode("utf-8")
docs = [{"raw_text": text[i : i + 4000]} for i in range(0, len(text), 4000)][:200]
client.upload_documents_batch(corpus["id"], docs)
client.build_indexes(corpus["id"])
client.build_and_start_tuning_run(corpus["id"])
print(client.search(corpus_id=corpus["id"], query="rabbit hole", top_k=3))
```
