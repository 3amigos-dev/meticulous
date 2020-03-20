"""
Testing for multithread management
"""

from unittest import mock

from meticulous._multiworker import main, update_workload


def test_empty_load():
    """
    Check updating an empty task list adds 3 repository load tasks
    """
    # Setup
    initial = []
    # Exercise
    result = update_workload(initial)
    # Verify
    check = [1 for elem in result if elem["name"] == "repository_load"]
    assert len(check) == 3  # noqa=S101 # nosec


@mock.patch("meticulous._multiworker.get_json_value")
@mock.patch("meticulous._multiworker.set_json_value")
@mock.patch("meticulous._controller.Controller.run")
def test_main(run_mock, set_mock, get_mock):
    """
    Main task should load from storage, update the workload and pass off
    handling to the controller and on termination save the result
    """
    # Setup
    final = []

    def saver(_, workload):
        final.extend(workload)
        return workload

    run_mock.return_value = [{}]
    get_mock.return_value = []
    set_mock.side_effect = saver
    # Exercise
    main()
    # Verify
    assert len(final) > 0  # noqa=S101 # nosec
