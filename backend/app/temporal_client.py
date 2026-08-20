from temporalio.client import Client

from app.config import settings


async def connect_temporal_client() -> Client:
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )