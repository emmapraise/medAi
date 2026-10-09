# Backwards compatibility facade for Medical Agent
from app.agent import GraphState, MedicalAgentService, NodeName, agent_service

__all__ = ["GraphState", "NodeName", "MedicalAgentService", "agent_service"]
