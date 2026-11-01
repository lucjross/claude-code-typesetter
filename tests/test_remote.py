"""--remote: keep claude running with no window connected."""
import asyncio

from typesetter import server


def detach_last(keep_alive):
    async def run():
        session = server.Session(["true"], lambda: None, keep_alive=keep_alive)
        ws = object()
        session.attach(ws)
        session.detach(ws)
        scheduled = session.idle_task is not None
        if session.idle_task:
            session.idle_task.cancel()
        return scheduled
    return asyncio.run(run())


def test_closing_the_last_window_schedules_exit_by_default():
    assert detach_last(keep_alive=False)


def test_remote_keeps_claude_running_with_no_window():
    assert not detach_last(keep_alive=True)


def test_remote_flag_is_ours_not_claudes():
    args, extra = server.parse_args(["--remote", "--resume"])
    assert args.remote
    assert extra == ["--resume"]
