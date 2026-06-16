# Multimedia Analytics

Interactive Visual Grounding of LLM Responses in Multimodal Knowledge Graphs

## Repo structure

- `mma2025/` — Plotly/Dash frontend app
- `offline/` — offline data pipeline (KG subset construction from DBpedia + LC-QuAD)

Large language models confidently produce answers but how do you know which facts they actually retrieved from structured knowledge, which facts they obtained using reasoning to provide valid answers, versus which ones they made up? Knowledge graphs (KGs) store high-quality factual triples about entities in the world, and multimodal KGs attach images and text to each entity, making them a rich substrate for multimedia analytics. Yet, the connection between what an LLM says and what the KG actually contains hasn’t been made visually inspectable.

This project closes this gap. It is an interactive visual analytics dashboard that lets users ask natural language questions over a multimodal KG, reads the LLM’s answer claim by claim, and visually maps each claim back to its supporting KG triple or flags it as hallucinated. Users can then explore the subgraph, identify gaps in the KG’s multimodal coverage, add missing triples, and regenerate the answer to see hallucinations resolve in real time.

The project is anchored in three open questions at the intersection of KG completeness, LLM reliability, and interactive visual analytics:

        Where do LLMs hallucinate? Can claim-level attribution against KG triples reliably identify hallucinated versus grounded sentences, and can a visual interface make this legible to a non-expert?
        Where is the KG incomplete? Which entities in a multimodal KG lack visual or textual grounding, and does missing modality coverage predict LLM hallucination on queries about those entities?
        Can interactive repair reduce hallucinations? If a user adds a missing triple interactively, does re-grounding measurably reduce unsupported claims in the regenerated answer?

[1] Guan, X., et al. Knowledge Graph-based Retrofitting for LLM Hallucination Mitigation. In Proceedings of the AAAI Conference on Artificial Intelligence (AAAI), 2024.

[2] Ma, J., et al. VISA: Retrieval-Augmented Generation with Visual Source Attribution. arXiv preprint arXiv:2412.14457, 2024.

[3] Li, H., et al. LLMs as Knowledge Graph Visual Analysis Assistants: A Preliminary Roadmap. In IEEE Visualization and Visual Analytics (VIS), 2024.
