"""Environments that are not Gymnasium's own, wrapped as Gymnasium environments so the adapter needs nothing new.

    make("arc3:LS20")   an ARC-AGI-3 game, by title, from the games built into the image (training games only)
    make(ID)            anything Gymnasium knows (Minigrid's BabyAI levels among them)
"""
import gymnasium as gym


def make(env_id: str, **kw):
    if env_id.startswith("arc3:"):
        from metasoar.envs.arc3 import Arc3Env
        return Arc3Env(env_id.split(":", 1)[1], **kw)
    import minigrid  # noqa: F401 - registers MiniGrid and BabyAI
    return gym.make(env_id, **kw)
