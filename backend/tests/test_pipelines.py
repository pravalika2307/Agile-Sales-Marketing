"""Integration tests for Pipelines, Pipeline Stages, and Default Pipeline provisioning."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.crm import Pipeline, PipelineStage


# ── SQLite Database Fixture ───────────────────────────────────────────────────

@pytest.fixture
def test_db_session():
    """Create fresh isolated in-memory SQLite database session for each test."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.pop(get_db, None)


@asynccontextmanager
async def make_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def register_tenant(client: AsyncClient, email: str, org_name: str) -> str:
    """Helper to register a tenant and return access token."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Pipeline Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


# ── Default Pipeline Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_new_organization_receives_default_pipeline_and_stages(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "alice@defaultpipe.com", "Default Pipe Org")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/pipelines", headers=headers)
        assert resp.status_code == 200
        pipelines = resp.json()
        assert len(pipelines) == 1
        default_pipe = pipelines[0]
        assert default_pipe["name"] == "Default Sales Pipeline"
        assert default_pipe["is_default"] is True

        # Check the 5 default stages
        stages = default_pipe["stages"]
        assert len(stages) == 5
        assert stages[0]["name"] == "Discovery"
        assert stages[0]["order_index"] == 1
        assert stages[0]["probability_pct"] == 10

        assert stages[1]["name"] == "Qualified"
        assert stages[1]["order_index"] == 2
        assert stages[1]["probability_pct"] == 25

        assert stages[2]["name"] == "Demo"
        assert stages[2]["order_index"] == 3
        assert stages[2]["probability_pct"] == 50

        assert stages[3]["name"] == "Proposal"
        assert stages[3]["order_index"] == 4
        assert stages[3]["probability_pct"] == 70

        assert stages[4]["name"] == "Won"
        assert stages[4]["order_index"] == 5
        assert stages[4]["probability_pct"] == 100


# ── Pipeline CRUD Tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_list_pipelines(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "bob@pipelines.com", "Pipeline Corp")
        headers = {"Authorization": f"Bearer {token}"}

        # Create custom pipeline
        create_resp = await client.post(
            "/api/v1/pipelines",
            json={"name": "Enterprise Outbound", "is_default": False},
            headers=headers,
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["name"] == "Enterprise Outbound"
        assert created["is_default"] is False

        # List pipelines - should now have default and enterprise
        list_resp = await client.get("/api/v1/pipelines", headers=headers)
        assert list_resp.status_code == 200
        pipes = list_resp.json()
        assert len(pipes) == 2
        # Default pipeline should be first
        assert pipes[0]["is_default"] is True


@pytest.mark.asyncio
async def test_get_and_update_pipeline(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "carol@pipelines.com", "Carol Corp")
        headers = {"Authorization": f"Bearer {token}"}

        # Get default pipeline
        list_resp = await client.get("/api/v1/pipelines", headers=headers)
        pipe_id = list_resp.json()[0]["id"]

        get_resp = await client.get(f"/api/v1/pipelines/{pipe_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == pipe_id
        assert len(get_resp.json()["stages"]) == 5

        # Update pipeline name
        patch_resp = await client.patch(
            f"/api/v1/pipelines/{pipe_id}",
            json={"name": "Primary Sales Flow"},
            headers=headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["name"] == "Primary Sales Flow"


@pytest.mark.asyncio
async def test_delete_pipeline(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "dan@pipelines.com", "Dan Corp")
        headers = {"Authorization": f"Bearer {token}"}

        # Create new pipeline to delete
        create_resp = await client.post(
            "/api/v1/pipelines",
            json={"name": "Temporary Pipeline"},
            headers=headers,
        )
        pipe_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/v1/pipelines/{pipe_id}", headers=headers)
        assert del_resp.status_code == 204

        # Verify 404
        get_resp = await client.get(f"/api/v1/pipelines/{pipe_id}", headers=headers)
        assert get_resp.status_code == 404


# ── Stage CRUD & Ordering Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_order_stages(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "eve@stages.com", "Eve Corp")
        headers = {"Authorization": f"Bearer {token}"}

        # Create new pipeline
        create_pipe_resp = await client.post(
            "/api/v1/pipelines",
            json={"name": "Custom Flow"},
            headers=headers,
        )
        pipe_id = create_pipe_resp.json()["id"]

        # Add stage 2
        s2 = await client.post(
            f"/api/v1/pipelines/{pipe_id}/stages",
            json={"name": "Evaluation", "order_index": 2, "probability_pct": 50},
            headers=headers,
        )
        assert s2.status_code == 201

        # Add stage 1
        s1 = await client.post(
            f"/api/v1/pipelines/{pipe_id}/stages",
            json={"name": "Initial Contact", "order_index": 1, "probability_pct": 10},
            headers=headers,
        )
        assert s1.status_code == 201

        # List stages for pipeline - should be ordered by order_index
        stages_resp = await client.get(f"/api/v1/pipelines/{pipe_id}/stages", headers=headers)
        assert stages_resp.status_code == 200
        stages = stages_resp.json()
        assert len(stages) == 2
        assert stages[0]["name"] == "Initial Contact"
        assert stages[1]["name"] == "Evaluation"


@pytest.mark.asyncio
async def test_update_and_delete_stage(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "frank@stages.com", "Frank Corp")
        headers = {"Authorization": f"Bearer {token}"}

        # Get default pipeline and first stage
        pipes_resp = await client.get("/api/v1/pipelines", headers=headers)
        first_stage = pipes_resp.json()[0]["stages"][0]
        stage_id = first_stage["id"]

        # Update stage
        patch_resp = await client.patch(
            f"/api/v1/pipeline-stages/{stage_id}",
            json={"name": "Deep Discovery", "probability_pct": 15},
            headers=headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["name"] == "Deep Discovery"
        assert patch_resp.json()["probability_pct"] == 15

        # Delete stage
        del_resp = await client.delete(f"/api/v1/pipeline-stages/{stage_id}", headers=headers)
        assert del_resp.status_code == 204

        # Second delete should return 404
        del_again = await client.delete(f"/api/v1/pipeline-stages/{stage_id}", headers=headers)
        assert del_again.status_code == 404


@pytest.mark.asyncio
async def test_stage_probability_validation(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "grace@stages.com", "Grace Corp")
        headers = {"Authorization": f"Bearer {token}"}

        pipes_resp = await client.get("/api/v1/pipelines", headers=headers)
        pipe_id = pipes_resp.json()[0]["id"]

        # Probability > 100 rejected
        bad_high = await client.post(
            f"/api/v1/pipelines/{pipe_id}/stages",
            json={"name": "Over 100", "order_index": 1, "probability_pct": 105},
            headers=headers,
        )
        assert bad_high.status_code == 422

        # Probability < 0 rejected
        bad_low = await client.post(
            f"/api/v1/pipelines/{pipe_id}/stages",
            json={"name": "Under 0", "order_index": 1, "probability_pct": -5},
            headers=headers,
        )
        assert bad_low.status_code == 422


# ── Multi-Tenant Isolation Tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_multi_tenant_isolation(test_db_session):
    async with make_client() as client:
        token_a = await register_tenant(client, "user_a@tenant.com", "Org Alpha")
        token_b = await register_tenant(client, "user_b@tenant.com", "Org Beta")

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant A gets their pipeline and stage
        resp_a = await client.get("/api/v1/pipelines", headers=headers_a)
        pipe_a_id = resp_a.json()[0]["id"]
        stage_a_id = resp_a.json()[0]["stages"][0]["id"]

        # Tenant B cannot access Tenant A's pipeline
        get_b = await client.get(f"/api/v1/pipelines/{pipe_a_id}", headers=headers_b)
        assert get_b.status_code == 404

        # Tenant B cannot update Tenant A's pipeline
        patch_b = await client.patch(
            f"/api/v1/pipelines/{pipe_a_id}",
            json={"name": "Hacked Pipeline"},
            headers=headers_b,
        )
        assert patch_b.status_code == 404

        # Tenant B cannot delete Tenant A's pipeline
        del_b = await client.delete(f"/api/v1/pipelines/{pipe_a_id}", headers=headers_b)
        assert del_b.status_code == 404

        # Tenant B cannot add stage to Tenant A's pipeline
        add_stage_b = await client.post(
            f"/api/v1/pipelines/{pipe_a_id}/stages",
            json={"name": "Injected Stage", "order_index": 10, "probability_pct": 50},
            headers=headers_b,
        )
        assert add_stage_b.status_code == 404

        # Tenant B cannot update Tenant A's stage
        patch_stage_b = await client.patch(
            f"/api/v1/pipeline-stages/{stage_a_id}",
            json={"name": "Hacked Stage"},
            headers=headers_b,
        )
        assert patch_stage_b.status_code == 404

        # Tenant B cannot delete Tenant A's stage
        del_stage_b = await client.delete(f"/api/v1/pipeline-stages/{stage_a_id}", headers=headers_b)
        assert del_stage_b.status_code == 404
