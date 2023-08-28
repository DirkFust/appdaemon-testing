import uuid
from datetime import datetime, timedelta
from math import floor
from typing import Any

import pytest
import appdaemon.plugins.hass.hassapi as hass
from freezegun import freeze_time

from appdaemon_testing import HassDriver
from appdaemon_testing.pytest import automation_fixture

BASE_DATE = datetime(2000, 5, 10, 12)
BASE_DATE_ADD_5 = BASE_DATE + timedelta(minutes=5)
BASE_DATE_ADD_10 = BASE_DATE + timedelta(minutes=10)
BASE_DATE_ADD_20 = BASE_DATE + timedelta(minutes=20)


def test_should_initialize_with_datetime_now(hass_driver):
    assert hass_driver.simulation_time == BASE_DATE


def test_should_timetravel_to_new_datetime(hass_driver):
    # ASSEMBLE
    new_time = BASE_DATE + timedelta(hours=10)

    # ACT
    hass_driver.time_travel_to(new_time)

    # ASSERT
    assert hass_driver.simulation_time == new_time


def test_should_raise_on_timetravel_to_the_past(hass_driver):
    # ASSEMBLE
    new_time_in_past = BASE_DATE - timedelta(hours=10)

    # ACT
    with pytest.raises(ValueError):
        hass_driver.time_travel_to(new_time_in_past)


def test_should_do_nothing_on_timetravel_to_same_time(hass_driver):
    # ASSEMBLE
    my_value = 0

    def my_callback(self, args):
        nonlocal my_value
        my_value += 1

    new_time = hass_driver.simulation_time
    run_at = hass_driver.get_mock("run_at")

    run_at(my_callback, new_time)

    # ACT
    hass_driver.time_travel_to(new_time)

    # ASSERT
    assert my_value == 0


def test_should_run_provided_method_on_timetravel(hass_driver):
    # ASSEMBLE
    my_value = 0

    def my_callback(**kwargs):
        nonlocal my_value
        my_value += 1

    new_time = BASE_DATE_ADD_10
    run_at = hass_driver.get_mock("run_at")

    run_at(my_callback, new_time)

    # ACT
    hass_driver.time_travel_to(new_time)

    # ASSERT
    assert my_value == 1


@pytest.mark.parametrize(
    "args",
    [
        {"value": 1},
        {"value": "2"},
        {"value": BASE_DATE},
        {"int": 1, "string": "string"}

    ]
)
def test_should_run_provided_method_with_args_on_timetravel(hass_driver, args):
    # ASSEMBLE
    my_value = 0

    def my_callback(**kwargs):
        nonlocal my_value
        my_value = kwargs

    new_time = BASE_DATE_ADD_10
    run_at = hass_driver.get_mock("run_at")

    run_at(my_callback, new_time, **args)

    # ACT
    hass_driver.time_travel_to(new_time)

    # ASSERT
    assert my_value == args


@pytest.mark.parametrize(
    "start,interval_sec,jump_to,expected",
    [
        pytest.param(BASE_DATE_ADD_10, 90, BASE_DATE_ADD_5, 0, id="run_every 90sec starting 12:10, jump to 12:05"),
        pytest.param(BASE_DATE_ADD_10, 90, BASE_DATE_ADD_10, 1, id="run_every 90sec starting 12:10, jump to 12:10"),
        pytest.param(BASE_DATE_ADD_10, 90, BASE_DATE_ADD_10 + timedelta(minutes=5), 4,
                     id="run_every 90sec starting 12:10, jump to 12:15"),
        pytest.param(BASE_DATE_ADD_10, 90, BASE_DATE_ADD_10 + timedelta(minutes=6), 5,
                     id="run_every 90sec starting 12:10, jump to 12:16"),
        pytest.param(BASE_DATE_ADD_10, 1, BASE_DATE_ADD_10 + timedelta(minutes=1), 61,
                     id="run_every sec starting 12:10, jump to 12:11"),
        pytest.param(BASE_DATE_ADD_10, 20, BASE_DATE_ADD_10 + timedelta(minutes=1), 4,
                     id="run_every 20sec starting 12:10, jump to 12:11"),
        pytest.param(BASE_DATE_ADD_10, 20, BASE_DATE_ADD_10 + timedelta(seconds=59), 3,
                     id="run_every 20sec starting 12:10, jump to 12:10:59"),
    ]
)
def test_should_run_callback_every_x_seconds(hass_driver, start: datetime, interval_sec: int, jump_to: datetime,
                                             expected):
    # ASSEMBLE
    my_value = 0

    def my_callback(**kwargs):
        nonlocal my_value
        my_value += 1

    run_every = hass_driver.get_mock("run_every")

    run_every(my_callback, start, interval_sec)

    # ACT
    hass_driver.time_travel_to(jump_to)

    # ASSERT
    assert my_value == expected


@pytest.mark.parametrize(
    "minutes",
    [
        # event is scheduled for 10 and every 5min afterward, so 15, 20, etc
        [1, 9, 11, 14, 15, 16],
        [16],
        list(range(1, 20)),
        [21, 24, 25]
    ]
)
def test_should_run_callback_every_x_seconds_the_right_amount_of_times(hass_driver, minutes):
    # ASSEMBLE
    my_value = 0

    def my_callback(**kwargs):
        nonlocal my_value
        my_value += 1

    run_every = hass_driver.get_mock("run_every")

    run_every(my_callback, BASE_DATE_ADD_10, 300)

    for minute in minutes:
        jump_to = BASE_DATE + timedelta(minutes=minute)
        expected_calls = 0
        if minute > 9:
            expected_calls = floor(minute / 5) - 1

        # ACT
        hass_driver.time_travel_to(jump_to)

        # ASSERT
        assert my_value == expected_calls


@pytest.mark.parametrize(
    "method,param,time,expected",
    [
        pytest.param("run_at", BASE_DATE_ADD_10, BASE_DATE_ADD_10, 1, id="run_at 12:10, jump to 12:10"),
        pytest.param("run_at", BASE_DATE_ADD_10, BASE_DATE_ADD_20, 1, id="run_at 12:10, jump to 12:20"),
        pytest.param("run_at", BASE_DATE_ADD_10, BASE_DATE_ADD_5, 0, id="run_at 12:10, jump_to 12:05"),
        pytest.param("run_once", BASE_DATE_ADD_10, BASE_DATE_ADD_10, 1, id="run_once 12:10, jump to 12:10"),
        pytest.param("run_once", BASE_DATE_ADD_10, BASE_DATE_ADD_20, 1, id="run_once 12:10, jump to 12:20"),
        pytest.param("run_once", BASE_DATE_ADD_10, BASE_DATE_ADD_5, 0, id="run_once 12:10, jump_to 12:05"),
        pytest.param("run_in", 600, BASE_DATE_ADD_10, 1, id="run_in 10min, jump 10min"),
        pytest.param("run_in", 600, BASE_DATE_ADD_20, 1, id="run_in 10min, jump 20min"),
        pytest.param("run_in", 600, BASE_DATE + timedelta(minutes=5), 0, id="run_in 10min, jump 5min"),
        pytest.param("run_daily", BASE_DATE_ADD_10, BASE_DATE_ADD_5, 0, id="run_daily at 12:10, jump to 12:05"),
        pytest.param("run_daily", BASE_DATE_ADD_10, BASE_DATE_ADD_10, 1, id="run_daily at 12:10, jump to 12:10"),
        pytest.param("run_daily", BASE_DATE_ADD_10, BASE_DATE_ADD_20, 1, id="run_daily at 12:10, jump to 12:20"),
        pytest.param("run_daily", BASE_DATE_ADD_10, BASE_DATE_ADD_10 + timedelta(days=1), 2,
                     id="run_daily at 12:10, jump to next day 12:10"),
        pytest.param("run_daily", BASE_DATE_ADD_10, BASE_DATE_ADD_10 + timedelta(days=2), 3,
                     id="run_daily at 12:10, jump to day after next 12:10"),
        pytest.param("run_hourly", BASE_DATE_ADD_10, BASE_DATE_ADD_5, 0, id="run_hourly starting 12:10, jump to 12:05"),
        pytest.param("run_hourly", BASE_DATE_ADD_10, BASE_DATE_ADD_10, 1,
                     id="run_hourly starting 12:10, jump to 12:10"),
        pytest.param("run_hourly", BASE_DATE_ADD_10, BASE_DATE_ADD_20, 1,
                     id="run_hourly starting 12:10, jump to 12:20"),
        pytest.param("run_hourly", BASE_DATE_ADD_10, BASE_DATE_ADD_10 + timedelta(hours=1), 2,
                     id="run_hourly starting 12:10, jump to 13:10"),
        pytest.param("run_hourly", BASE_DATE_ADD_10, BASE_DATE_ADD_10 + timedelta(hours=2), 3,
                     id="run_hourly starting 12:10, jump to 14:10"),
        pytest.param("run_minutely", BASE_DATE_ADD_10, BASE_DATE_ADD_5, 0,
                     id="run_minutely starting 12:10, jump to 12:05"),
        pytest.param("run_minutely", BASE_DATE_ADD_10, BASE_DATE_ADD_10, 1,
                     id="run_minutely starting 12:10, jump to 12:10"),
        pytest.param("run_minutely", BASE_DATE_ADD_10, BASE_DATE_ADD_20, 11,
                     id="run_minutely starting 12:10, jump to 12:20"),
        pytest.param("run_minutely", BASE_DATE_ADD_10 + timedelta(seconds=-30), BASE_DATE_ADD_20, 11,
                     id="run_minutely starting 12:09:30, jump to 12:20"),
        pytest.param("run_minutely", BASE_DATE_ADD_10 + timedelta(seconds=-30),
                     BASE_DATE_ADD_10 + timedelta(seconds=45), 2,
                     id="run_minutely starting 12:09:30, jump to 12:10:45"),
    ]
)
def test_should_run_callback_at_specified_times(hass_driver, method: str, param: Any, time: datetime,
                                                expected):
    # ASSEMBLE
    my_value = 0

    def my_callback(**kwargs):
        nonlocal my_value
        my_value += 1

    _method = hass_driver.get_mock(method)

    _method(my_callback, param)

    # ACT
    hass_driver.time_travel_to(time)

    # ASSERT
    assert my_value == expected


def test_should_run_callback_at_specified_time_with__run_in(hass_driver):
    # ASSEMBLE
    my_value = 0

    def my_callback(**kwargs):
        nonlocal my_value
        my_value += 1

    new_time = BASE_DATE_ADD_10
    run_at = hass_driver.get_mock("run_at")

    run_at(my_callback, new_time)

    # ACT
    hass_driver.time_travel_to(new_time)

    # ASSERT
    assert my_value == 1


def test_appdaemon_time_methods_should_be_mocked(hass_driver):
    # ASSEMBLE
    _time = hass_driver.get_mock("time")
    _datetime = hass_driver.get_mock("datetime")
    _date = hass_driver.get_mock("date")

    # ASSERT
    assert _time() == BASE_DATE.time()
    assert _datetime() == BASE_DATE
    assert _date() == BASE_DATE.date()


@pytest.mark.parametrize(
    "add_minutes",
    [
        # event is scheduled for 10, so everything smaller is before, everything larger after
        [10, 20],
        [10, 10, 10, 20],
        list(range(1, 20)),
        [11, 23, 24],
        [5, 7, 15, 18]
    ]
)
def test_event_scheduled_at_fixed_time_should_only_run_once(hass_driver, add_minutes):
    # ASSEMBLE
    my_value = 0
    scheduled_time = BASE_DATE_ADD_10

    def my_callback(**kwargs):
        nonlocal my_value
        my_value += 1

    run_at = hass_driver.get_mock("run_at")

    run_at(my_callback, scheduled_time)

    for minutes in add_minutes:
        time = BASE_DATE + timedelta(minutes=minutes)

        # ACT
        hass_driver.time_travel_to(time)

        # ASSERT
        assert my_value == (1 if time >= scheduled_time else 0)


@pytest.mark.parametrize(
    "method,param",
    [
        pytest.param("run_at", BASE_DATE_ADD_10),
        pytest.param("run_once", BASE_DATE_ADD_10),
        pytest.param("run_in", 600),
        pytest.param("run_daily", BASE_DATE_ADD_10),
        pytest.param("run_hourly", BASE_DATE_ADD_10),
        pytest.param("run_minutely", BASE_DATE_ADD_10),
        pytest.param("run_minutely", BASE_DATE_ADD_10),
        pytest.param("run_minutely", BASE_DATE_ADD_10),
        pytest.param("run_at_sunrise", None),
        pytest.param("run_at_sunset", None),
    ],
    ids=lambda p: p if type(p) is str else ""
)
def test_scheduling_a_callback_should_return_a_handle(hass_driver, method, param):
    # ASSEMBLE
    def my_callback(**kwargs):
        pass

    method_ = hass_driver.get_mock(method)

    # ACT
    if param:
        handle = method_(my_callback, param)
    else:
        handle = method_(my_callback)

    # ASSERT
    assert type(handle) is str
    assert uuid.UUID(handle)


def test_should_cancel_timer(hass_driver):
    # ASSEMBLE
    my_value = 0
    scheduled_time = BASE_DATE_ADD_10

    def my_callback(**kwargs):
        nonlocal my_value
        my_value += 1

    run_at = hass_driver.get_mock("run_at")
    cancel_timer = hass_driver.get_mock("cancel_timer")
    handle = run_at(my_callback, scheduled_time)

    # ACT
    cancel_timer(handle)
    hass_driver.time_travel_to(BASE_DATE_ADD_20)

    # ASSERT
    assert my_value == 0


def test_should_call_multiple_timers_of_different_kinds(hass_driver):
    my_value1 = 0
    my_value2 = 0

    def my_callback1(**kwargs):
        nonlocal my_value1
        my_value1 += 1

    def my_callback2(**kwargs):
        nonlocal my_value2
        my_value2 += 1

    run_at = hass_driver.get_mock("run_at")
    run_every = hass_driver.get_mock("run_every")

    run_at(my_callback1, BASE_DATE_ADD_10)
    run_every(my_callback2, BASE_DATE_ADD_5, 300)

    # ACT / ASSERT
    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=2))
    assert my_value1 == 0
    assert my_value2 == 0

    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=5))
    assert my_value1 == 0
    assert my_value2 == 1

    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=7))
    assert my_value1 == 0
    assert my_value2 == 1

    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=10))
    assert my_value1 == 1
    assert my_value2 == 2

    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=13))
    assert my_value1 == 1
    assert my_value2 == 2

    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=15))
    assert my_value1 == 1
    assert my_value2 == 3


def test_should_call_multiple_timers_of_same_kind(hass_driver):
    my_value = 0

    def my_callback(**kwargs):
        nonlocal my_value
        my_value += 1

    run_every = hass_driver.get_mock("run_every")

    run_every(my_callback, BASE_DATE_ADD_5, 300)
    run_every(my_callback, BASE_DATE_ADD_5, 300)

    # ACT / ASSERT
    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=2))
    assert my_value == 0

    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=5))
    assert my_value == 2

    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=7))
    assert my_value == 2

    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=10))
    assert my_value == 4

    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=13))
    assert my_value == 4

    hass_driver.time_travel_to(BASE_DATE + timedelta(minutes=15))
    assert my_value == 6


@pytest.mark.parametrize(
    "missing_test",
    [
        "run_at_sunset (repeating)",
        "run_at_sunrise (repeating)",
        "use other inputs of methods for start time ( iso-strings etc)",
    ]
)
def test_missing_tests(missing_test):
    # ASSEMBLE

    # ACT

    # ASSERT
    pytest.fail(missing_test)


class MyTestApp(hass.Hass):
    def initialize(self):
        start = self.datetime() + timedelta(minutes=10)
        self.run_every(self.scheduler_callback, start, 300)

    def scheduler_callback(self, **kwargs):
        self.log(f"scheduler! {kwargs=} ", level="INFO")


def test_with_app(hass_driver, my_test_app: MyTestApp):
    # ASSEMBLE
    log = hass_driver.get_mock("log")
    start = BASE_DATE

    # ACT / ASSERT
    hass_driver.time_travel_to(start + timedelta(minutes=1))
    log.assert_not_called()

    hass_driver.time_travel_to(start + timedelta(minutes=9))
    log.assert_not_called()

    hass_driver.time_travel_to(start + timedelta(minutes=10))
    log.assert_called_once()

    hass_driver.time_travel_to(start + timedelta(minutes=14))
    log.assert_called_once()

    hass_driver.time_travel_to(start + timedelta(minutes=26))
    assert log.call_count == 4  # called on 10, 15, 20 and 25


@automation_fixture(MyTestApp)
def my_test_app():
    pass


@pytest.fixture
@freeze_time(BASE_DATE)
def hass_driver() -> HassDriver:
    hass_driver = HassDriver()
    hass_driver.inject_mocks()
    return hass_driver
