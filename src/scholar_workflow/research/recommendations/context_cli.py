"""Thin headless interfaces for routed tasks, central feedback and Zotero intake."""

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

    @group.group(name="tasks")
    def task_group():
        """Bind an original chat and locate its two project Markdown files."""

    @task_group.command(name="list")
    @click.option("--project-id")
    @click.pass_obj
    @guarded
    def list_tasks(context, project_id):
        output(tasks(context).list(project_id))

    @task_group.command(name="bind")
    @click.option("--input", "input_path", required=True)
    @click.pass_obj
    @guarded
    def bind(context, input_path):
        payload = read_input(input_path)
        required = {"project_root", "producer_id", "title", "thread_id", "expected_revision"}
        if not required <= set(payload) <= required | {"host"}:
            raise ResearchError("Task binding needs project_root, producer_id, title, thread_id and expected_revision; host is optional.")
        output(tasks(context).bind(**payload))

    @task_group.command(name="guide")
    @click.argument("producer_id")
    @click.option("--read-context", is_flag=True, help="Expand the selected task's context.md and recommended.md only.")
    @click.pass_obj
    @guarded
    def guide(context, producer_id, read_context):
        output(tasks(context).guide(producer_id, include_context=read_context))

    @group.group(name="feedback")
    def feedback_group():
        """Inspect/recover automatic human-feedback delivery without an agent."""

    @feedback_group.command(name="status")
    @click.pass_obj
    @guarded
    def feedback_status(context):
        output(Feedback(store_for(context)).status())

    @feedback_group.command(name="deliveries")
    @click.option("--producer-id")
    @click.option("--event-id")
    @click.pass_obj
    @guarded
    def deliveries(context, producer_id, event_id):
        output(Feedback(store_for(context)).deliveries(producer_id=producer_id, event_id=event_id))

    @feedback_group.command(name="start")
    @click.option("--input", "input_path", required=True)
    @click.pass_obj
    @guarded
    def start(context, input_path):
        payload = read_input(input_path)
        if set(payload) != {"event_id", "producer_id"}:
            raise ResearchError("A start receipt needs event_id and producer_id.")
        output(Feedback(store_for(context)).start(**payload))

    @feedback_group.command(name="complete")
    @click.option("--input", "input_path", required=True)
    @click.pass_obj
    @guarded
    def complete(context, input_path):
        payload = read_input(input_path)
        if set(payload) != {"event_id", "producer_id", "context_digest", "summary"}:
            raise ResearchError("Completion needs event_id, producer_id, context_digest and summary.")
        output(Feedback(store_for(context)).complete(**payload))

    @feedback_group.command(name="retry")
    @click.option("--input", "input_path", required=True)
    @click.pass_obj
    @guarded
    def retry(context, input_path):
        payload = read_input(input_path)
        if set(payload) != {"event_id", "producer_id", "expected_attempts", "confirmed_not_queued"}:
            raise ResearchError("Retry needs event_id, producer_id, expected_attempts and confirmed_not_queued.")
        output(Feedback(store_for(context)).retry(**payload))

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
