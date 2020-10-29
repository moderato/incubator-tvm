# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

""" Serialization and other I/O support for measurement records (tuning logs). """

import numpy as np

import tvm._ffi
from tvm.runtime import Object
from .compute_dag import ComputeDAG
from .measure import MeasureErrorNo, MeasureInput, MeasureCallback
from .search_task import SearchTask
from . import _ffi_api


@tvm._ffi.register_object("auto_scheduler.RecordToFile")
class RecordToFile(MeasureCallback):
    """
    A measurement callback that writes measurement records into a file.

    Parameters
    ----------
    filename : str
        File name for this callback to write log to.
    """

    def __init__(self, filename="auto_scheduler_tuning.json"):
        self.__init_handle_by_constructor__(_ffi_api.RecordToFile, filename)


@tvm._ffi.register_object("auto_scheduler.RecordReader")
class RecordReader(Object):
    """
    Reader of the json log file.

    Parameters
    ----------
    filename : str = "auto_scheduler_tuning.json"
        File name for this reader to load log from.
    """

    def __init__(self, filename="auto_scheduler_tuning.json"):
        self.__init_handle_by_constructor__(_ffi_api.RecordReader, filename)

    def read_lines(self, max_lines=None, skip_lines=0):
        """Read multiple lines from the log file.

        Parameters
        ----------
        max_lines : Optional[int]
            The maximum number of lines. None to read all lines.
        skip_lines : int = 0
            Skip the first n lines.

        Returns
        -------
        inputs : List[auto_scheduler.measure.MeasureInput]
            The MeasureInputs loaded from the log file.
        results : List[auto_scheduler.measure.MeasureResult]
            The MeasureResults loaded from the log file.

        Notes
        -----
        Some unimportant and expensive fields in the returned MeasureInput are not deserialized
        for faster read speed (e.g. input.task.compute_dag, input.state.stages).
        If you want to use them, you can call the :code:`recover_measure_input` below
        to rebuild these fields.
        """
        inputs, results = _ffi_api.RecordReaderReadLines(
            self, max_lines if max_lines else -1, skip_lines
        )
        return inputs, results

    def __iter__(self):
        while True:
            ret = _ffi_api.RecordReaderReadNext(self)
            if not ret:
                break
            yield ret[0], ret[1]  # (input, result)


def load_records(filename):
    """
    Load measurement records from a file.

    Parameters
    ----------
    filename : str
        File name to load log from.

    Returns
    -------
    logs : List[auto_scheduler.measure.MeasureInput, auto_scheduler.measure.MeasureResult]

    Notes
    -----
    Some unimportant and expensive fields in the returned MeasureInput are not deserialized
    for faster read speed (e.g., input.task.compute_dag, input.state.stages).
    If you want to use them, you can call the :code:`recover_measure_input` below
    to rebuild these fields.
    """
    return zip(*RecordReader(filename).read_lines())


def save_records(filename, inputs, results):
    """
    Append measure records to file.

    Parameters
    ----------
    filename : str
        File name to write log to.
    inputs: List[MeasureInputs]
        The MeasureInputs to be written.
    results: List[MeasureResults]
        The MeasureResults to be written.
    """
    _ffi_api.SaveRecords(filename, inputs, results)


def load_best(filename, workload_key=None, target=None):
    """Return the best measurement pair form a log file. This may return none results if
    there is no legal measure pair with the specified workload_key/target found from the log file.

    Parameters
    ----------
    filename : str
        File name to load log from.
    workload_key : Optional[str]
        The workload key of the compute declaration.
        With `None`, this returns the best measure pair of all workloads.
    target : Optional[tvm.target.Target]
        The target device.
        With `None`, this returns the best measure pair of all target devices.

    Returns
    -------
    input : auto_scheduler.measure.MeasureInput
        The best State's MeasureInput from this log fine.
    result : auto_scheduler.measure.MeasureResult
        The best State's MeasureResult from this log fine.
    """
    log_reader = RecordReader(filename)
    best_cost = 1e30
    best_inp = None
    best_res = None

    for inp, res in log_reader:
        if res.error_no != MeasureErrorNo.NO_ERROR:
            continue
        if workload_key and inp.task.workload_key != workload_key:
            continue
        if target and inp.task.target.kind.name != target.kind.name:
            continue

        costs = [v.value for v in res.costs]
        cost = np.mean(costs)
        if cost < best_cost:
            best_cost = cost
            best_inp = inp
            best_res = res

    return best_inp, best_res


def recover_measure_input(inp, rebuild_state=False):
    """
    Recover a deserialized MeasureInput by rebuilding the missing fields.
    1. Rebuid the compute_dag in inp.task
    2. (Optional) Rebuild the stages in inp.state

    Parameters
    ----------
    inp: MeasureInput
        The deserialized MeasureInput
    rebuild_state: bool = False
        Whether rebuild the stages in MeasureInput.State

    Returns
    -------
    new_input: MeasureInput
        The fully recovered MeasureInput with all fields rebuilt.
    """
    task = inp.task
    new_task = SearchTask(
        ComputeDAG(task.workload_key),
        task.workload_key,
        task.target,
        task.target_host,
        task.hardware_params,
    )

    if rebuild_state:
        new_state = new_task.compute_dag.infer_bound_from_state(inp.state)
    else:
        new_state = inp.state

    return MeasureInput(new_task, new_state)
