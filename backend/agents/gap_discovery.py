"""
Agent 4: Gap Discovery.

Responsibility:
- Extract stated limitations from state["selected_papers"].
- Cluster similar limitations (sentence-transformers embeddings +
  scikit-learn clustering) to surface recurring themes.
- Write candidate research gaps to state["gaps"].
"""

from sklearn.cluster import AgglomerativeClustering
from sentence_transformers import SentenceTransformer

from llm.client import get_llm_client
from Nexora.backend.graph.state import ResearchState


async def gap_discovery(state: ResearchState) -> ResearchState:
    # TODO: extract limitation statements per paper via LLM
    # TODO: embed limitations and cluster to find recurring themes
    # TODO: synthesize clusters into candidate gaps, write to state["gaps"]
    raise NotImplementedError
