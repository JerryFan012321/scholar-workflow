"""Thin headless interfaces for project tasks, feedback and Zotero intake."""
from pathlib import Path

import click

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.feedback import Feedback
from scholar_workflow.research.recommendations.intake import IntakeQueue
from scholar_workflow.research.recommendations.project_tasks import ProjectTasks


def install(group, store_for, read_input, output, guarded):
    def tasks(context):
        return ProjectTasks(store_for(context), context["profile"])

    def intake(context):
        return IntakeQueue(store_for(context), context["profile"])

    @group.group(name="projects")
    def project_group():
        """Enable a selected project's optional recommendation component."""

    @project_group.command(name="enable")
    @click.option("--project-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
    @click.pass_obj
    @guarded
    def enable(context, project_root):
        output(tasks(context).enable(project_root))

    @group.group(name="tasks")
    def task_group():
        """Register stable project tasks without running an agent or reading background."""

    @task_group.command(name="list")
    @click.option("--project-id")
    @click.pass_obj
    @guarded
    def list_tasks(context, project_id):
        output(tasks(context).list(project_id))

    @task_group.command(name="register")
    @click.option("--input", "input_path", required=True)
    @click.pass_obj
    @guarded
    def register(context, input_path):
        payload = read_input(input_path)
        if set(payload) != {"project_id", "producer_id", "title", "expected_revision"}:
            raise ResearchError("Task registration needs project_id, producer_id, title and expected_revision.")
        output(tasks(context).register(**payload))

    @task_group.command(name="guide")
    @click.argument("producer_id")
    @click.option("--read-context", is_flag=True, help="Explicitly expand only this project's selected task context.")
    @click.pass_obj
    @guarded
    def guide(context, producer_id, read_context):
        output(tasks(context).guide(producer_id, include_context=read_context))

    @task_group.command(name="save-context")
    @click.option("--input", "input_path", required=True)
    @click.pass_obj
    @guarded
    def save_task_context(context, input_path):
        payload = read_input(input_path)
        if set(payload) != {"producer_id", "content", "expected_revision", "consumed_event_ids"}:
            raise ResearchError("Task context needs producer_id, content, expected_revision and explicit consumed_event_ids.")
        output(tasks(context).save_context(**payload))

    @group.group(name="feedback")
    def feedback_group():
        """Inspect/recover automatic human-feedback delivery without an agent."""

    @feedback_group.command(name="status")
    @click.pass_obj
    @guarded
    def feedback_status(context):
        output(Feedback(store_for(context)).status())

    @feedback_group.command(name="sync")
    @click.pass_obj
    @guarded
    def feedback_sync(context):
        result = Feedback(store_for(context)).flush()
        output(result)
        if result["pending_deliveries"]:
            click.get_current_context().exit(6)

    @feedback_group.command(name="events")
    @click.option("--producer-id")
    @click.option("--after", type=click.IntRange(min=0), default=0)
    @click.option("--pool-id", "expected_pool", help="Required when continuing a nonzero event sequence.")
    @click.option("--limit", type=click.IntRange(1, 1000), default=100)
    @click.pass_obj
    @guarded
    def events(context, producer_id, after, limit, expected_pool):
        output(Feedback(store_for(context)).events(producer_id=producer_id, after=after, limit=limit, expected_pool=expected_pool))

    @feedback_group.command(name="decision")
    @click.option("--input", "input_path", required=True)
    @click.pass_obj
    @guarded
    def decision(context, input_path):
        payload = read_input(input_path)
        required = {"candidate_id", "decision", "expected_revision"}
        if not required <= set(payload) <= required | {"reason", "scope"}:
            raise ResearchError("Decision needs candidate_id, decision and expected_revision; reason/scope are optional.")
        store = store_for(context)
        result = store.set_decision(**payload)
        IntakeQueue(store, context["profile"]).drain(limit=1)
        output(store.get_candidate(result["candidate_id"]))

    @group.group(name="curator")
    def curator_group():
        """Disclose shared preferences and a bounded unconsumed feedback batch."""

    @curator_group.command(name="batch")
    @click.option("--limit", type=click.IntRange(1, 1000), default=100)
    @click.pass_obj
    @guarded
    def batch(context, limit):
        output(Feedback(store_for(context)).batch(limit))

    @curator_group.command(name="consume")
    @click.option("--input", "input_path", required=True)
    @click.pass_obj
    @guarded
    def consume(context, input_path):
        payload = read_input(input_path)
        if set(payload) != {"batch_id", "content", "expected_revision", "updated_by"}:
            raise ResearchError("Consumption needs batch_id, preference content, expected_revision and updated_by.")
        output(Feedback(store_for(context)).consume(**payload))

    @group.group(name="intake")
    def intake_group():
        """Configure and execute metadata/opinion intake; never transfer original files."""

    @intake_group.command(name="target")
    @click.option("--input", "input_path", help="JSON collection_key, expected_revision, enabled; omit to read.")
    @click.pass_obj
    @guarded
    def target(context, input_path):
        service = intake(context)
        if input_path:
            payload = read_input(input_path)
            if set(payload) != {"collection_key", "expected_revision", "enabled"}:
                raise ResearchError("Intake target needs collection_key, expected_revision and enabled.")
            output(service.configure(**payload))
        else:
            output(service.configuration())

    @intake_group.command(name="process")
    @click.option("--limit", type=click.IntRange(1, 100), default=5)
    @click.option("--retry", is_flag=True, help="Retry attention/conflict entries only after inspecting their cause.")
    @click.pass_obj
    @guarded
    def process(context, limit, retry):
        result = intake(context).drain(limit=limit, retry=retry)
        output(result)
        if result["status"] == "partial":
            click.get_current_context().exit(6)

    @intake_group.command(name="history")
    @click.pass_obj
    @guarded
    def intake_history(context):
        output(intake(context).history())

    @intake_group.command(name="entries")
    @click.option("--limit", type=click.IntRange(1, 100), default=50)
    @click.option("--start", type=click.IntRange(min=0), default=0)
    @click.pass_obj
    @guarded
    def entries(context, limit, start):
        output(intake(context).entries(limit=limit, start=start))
