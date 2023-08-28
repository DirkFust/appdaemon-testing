import contextlib
import uuid
from datetime import datetime, timedelta
from functools import wraps
import logging
import unittest.mock as mock
from collections import defaultdict
from copy import copy
from dataclasses import InitVar, dataclass, field
from typing import Dict, Any, List, Callable, Union, Optional

import appdaemon.plugins.hass.hassapi as hass

_LOGGER = logging.getLogger(__name__)


def possible_side_effects_state_change(fn):
    """
    This attribute executes XXXXXXXX
    """

    @wraps(fn)
    def inner(self, *args, **kwargs):
        if self.update_states:
            fn(self, *args, **kwargs)

    return inner


@dataclass(frozen=True)
class StateSpy:
    callback: Callable
    attribute: Optional[str]
    new: Optional[str]
    old: Optional[str]
    kwargs: Any


@dataclass
class Scheduler:
    start: datetime
    frequency_sec: int
    callback: Callable
    kwargs: Any
    run_count: int = field(init=False, default=0)
    last_run: datetime = field(init=False, default=None)
    is_canceled: bool = field(init=False, default=False)

    def __post_init__(self):
        self.last_run = self.start


class HassDriver:
    def __init__(self, update_states: bool = True, base_date: Optional[datetime] = None):
        self._base_datetime = base_date if base_date is not None else datetime.now()
        self._current_datetime = self._base_datetime
        self._setup_active = False

        self._mocks = dict(
            log=mock.Mock(),
            error=mock.Mock(),
            call_service=mock.Mock(),
            cancel_timer=mock.Mock(side_effect=self._se_cancel_timer),
            timer_running=mock.Mock(),
            get_state=mock.Mock(side_effect=self._se_get_state),
            # TODO(NW): Implement side-effect for listen_event
            listen_event=mock.Mock(return_value=uuid.uuid4()),
            fire_event=mock.Mock(),
            listen_state=mock.Mock(side_effect=self._se_listen_state),
            notify=mock.Mock(),
            run_at=mock.Mock(side_effect=self._se_run_at),
            run_once=mock.Mock(side_effect=self._se_run_at),
            run_in=mock.Mock(side_effect=self._se_run_in),
            run_at_sunrise=mock.Mock(),
            run_at_sunset=mock.Mock(),
            run_daily=mock.Mock(side_effect=self._se_run_daily),
            run_every=mock.Mock(side_effect=self._se_run_every),
            run_hourly=mock.Mock(side_effect=self._se_run_hourly),
            run_minutely=mock.Mock(side_effect=self._se_run_minutely),
            set_state=mock.Mock(),
            time=mock.Mock(return_value=self.simulation_time.time()),
            datetime=mock.Mock(return_value=self.simulation_time),
            date=mock.Mock(return_value=self.simulation_time.date()),
            turn_off=mock.Mock(side_effect=self._se_turn_off),
            turn_on=mock.Mock(side_effect=self._se_turn_on),
        )

        self.update_states = update_states

        self._states: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"state": None})
        self._state_spys: Dict[Union[str, None], List[StateSpy]] = defaultdict(
            lambda: []
        )
        self._schedulers = {}

    @property
    def simulation_time(self):
        return self._current_datetime

    def time_travel_to(self, new_datetime: datetime):
        if new_datetime == self.simulation_time: return
        if new_datetime < self.simulation_time: raise ValueError(
            f"time travel is only possible to the future! You're trying to travel from {self.simulation_time} to {new_datetime}")

        callbacks_due = []
        for s in self._schedulers.values():
            if s.frequency_sec < 1 and (
                    s.is_canceled or
                    s.start < self.simulation_time or
                    s.start > new_datetime or
                    (s.start == self.simulation_time and s.run_count > 0)
            ): continue

            if s.frequency_sec < 1:
                callbacks_due.append((s.start, s.callback, s.kwargs))
                s.run_count += 1
            else:
                next_ = s.last_run
                while next_ <= new_datetime:
                    if next_ >= self.simulation_time:
                        callbacks_due.append((next_, s.callback, s.kwargs))
                        s.run_count += 1
                        s.last_run = s.last_run + timedelta(seconds=s.frequency_sec)
                    next_ = next_ + timedelta(seconds=s.frequency_sec)

        for _, callback, kwargs in sorted(callbacks_due, key=lambda x: x[0]):
            callback(**kwargs)

        self._current_datetime = new_datetime

    def get_mock(self, meth: str) -> mock.Mock:
        """
        Returns the mock associated with the provided AppDaemon method

        Parameters:
            meth: The method to retreive the mock implementation for
        """
        return self._mocks[meth]

    def inject_mocks(self) -> None:
        """
        Monkey-patch the AppDaemon hassapi.Hass base-class methods with mock
        implementations.
        """
        for meth_name, impl in self._mocks.items():
            if getattr(hass.Hass, meth_name) is None:
                raise AssertionError("Attempt to mock non existing method: ", meth_name)
            _LOGGER.debug("Patching hass.Hass.%s", meth_name)
            setattr(hass.Hass, meth_name, impl)

    @contextlib.contextmanager
    def setup(self):
        """
        A context manager to indicate that execution is taking place during a
        "setup" phase.

        This context manager can be used to configure/set up any existing states
        that might be required to run the test. State changes during execution within
        this context manager will cause `listen_state` handlers to not be called.

        Example:

        ```py
        def test_my_app(hass_driver, my_app: MyApp):
            with hass_driver.setup():
                # Any registered listen_state handlers will not be called
                hass_driver.set_state("binary_sensor.motion_detected", "off")

            # Respective listen_state handlers will be called
            hass_driver.set_state("binary_sensor.motion_detected", "on")
            ...
        ```
        """
        self._setup_active = True
        yield None
        self._setup_active = False

    def set_state(
            self, entity, state, *, attribute_name="state", previous=None, trigger=None, **kwargs
    ) -> None:
        """
        Update/set state of an entity.

        State changes will cause listeners (via listen_state) to be called on
        their respective state changes.

        Parameters:
            entity: The entity to update
            state: The state value to set
            attribute_name: The attribute to set
            previous: Forced previous value
            trigger: Whether this change should trigger registered listeners
                     (via listen_state)
        """
        if trigger is None:
            # Avoid triggering state changes during state setup phase
            trigger = not self._setup_active

        domain, _ = entity.split(".")
        state_entry = self._states[entity]
        prev_state = copy(state_entry)
        old_value = previous or prev_state.get(attribute_name)
        new_value = state

        if old_value == new_value:
            return

        # Update the state entry
        state_entry[attribute_name] = new_value

        if not trigger:
            return

        # Notify subscribers of the change
        for spy in self._state_spys[domain] + self._state_spys[entity]:
            sat_attr = spy.attribute == attribute_name or spy.attribute == "all"
            sat_new = spy.new is None or spy.new == new_value
            sat_old = spy.old is None or spy.old == old_value

            param_old = prev_state if spy.attribute == "all" else old_value
            param_new = copy(state_entry) if spy.attribute == "all" else new_value
            param_attribute = None if spy.attribute == "all" else attribute_name

            if all([sat_old, sat_new, sat_attr]):
                spy.callback(entity, param_attribute, param_old, param_new, spy.kwargs | kwargs)

    @possible_side_effects_state_change
    def _se_turn_off(self, entity_id=None, **kwargs):
        self.set_state(entity_id, "off", **kwargs)

    @possible_side_effects_state_change
    def _se_turn_on(self, entity_id=None, **kwargs):
        self.set_state(entity_id, "on", **kwargs)

    @possible_side_effects_state_change
    def _se_run_at(self, callback: Callable, start: Union[datetime, str], **kwargs):
        return self._set_scheduler(start, 0, callback, **kwargs)

    @possible_side_effects_state_change
    def _se_run_daily(self, callback: Callable, start: Union[datetime, str], **kwargs):
        return self._set_scheduler(start, 60 * 60 * 24, callback, **kwargs)

    @possible_side_effects_state_change
    def _se_run_hourly(self, callback: Callable, start: Union[datetime, str], **kwargs):
        return self._set_scheduler(start, 60 * 60, callback, **kwargs)

    @possible_side_effects_state_change
    def _se_run_minutely(self, callback: Callable, start: Union[datetime, str], **kwargs):
        return self._set_scheduler(start, 60, callback, **kwargs)

    @possible_side_effects_state_change
    def _se_run_every(self, callback: Callable, start: Union[datetime, str], interval: int, **kwargs):
        return self._set_scheduler(start, interval, callback, **kwargs)

    @possible_side_effects_state_change
    def _se_run_in(self, callback: Callable, delay: int, **kwargs):
        return self._set_scheduler(self._current_datetime + timedelta(seconds=delay), 0, callback, **kwargs)

    def _set_scheduler(self, start: datetime, frequency_sec: int, callback: Callable, **kwargs):
        handle = str(uuid.uuid4())
        self._schedulers[handle] = Scheduler(start, frequency_sec, callback, kwargs)
        return handle

    def _se_cancel_timer(self, handle):
        self._schedulers[handle].is_canceled = True

    def _se_get_state(self, entity_id=None, attribute="state", default=None, **kwargs):
        _LOGGER.debug("Getting state for entity: %s", entity_id)

        fully_qualified = "." in entity_id
        matched_states = {}
        if fully_qualified:
            matched_states[entity_id] = self._states[entity_id]
        else:
            for s_eid, state in self._states.items():
                domain, entity = s_eid.split(".")
                if domain == entity_id:
                    matched_states[s_eid] = state

        # With matched states, map the provided attribute (if applicable)
        if attribute != "all":
            matched_states = {
                eid: state.get(attribute) for eid, state in matched_states.items()
            }

        if default is not None:
            matched_states = {
                eid: state or default for eid, state in matched_states.items()
            }

        if fully_qualified:
            return matched_states[entity_id]
        else:
            return matched_states

    def _se_listen_state(
            self, callback, entity=None, attribute=None, new=None, old=None, **kwargs
    ):
        spy = StateSpy(
            callback=callback,
            attribute=attribute or "state",
            new=new,
            old=old,
            kwargs=kwargs,
        )
        self._state_spys[entity].append(spy)
        return uuid.uuid4()
