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
"""External function interface to CuDNN v7 library."""
# pylint: disable-msg=C0103
import ctypes
import numpy as np
import tvm

import tvm._ffi
from tvm import te

# algos can be read from cudnn.h
_FWD_ALGOS = [
    "CUDNN_CONVOLUTION_FWD_ALGO_IMPLICIT_GEMM",
    "CUDNN_CONVOLUTION_FWD_ALGO_IMPLICIT_PRECOMP_GEMM",
    "CUDNN_CONVOLUTION_FWD_ALGO_GEMM",
    "CUDNN_CONVOLUTION_FWD_ALGO_DIRECT",
    "CUDNN_CONVOLUTION_FWD_ALGO_FFT",
    "CUDNN_CONVOLUTION_FWD_ALGO_FFT_TILING",
    "CUDNN_CONVOLUTION_FWD_ALGO_WINOGRAD",
    "CUDNN_CONVOLUTION_FWD_ALGO_WINOGRAD_NONFUSED",
    "CUDNN_CONVOLUTION_FWD_ALGO_COUNT",
]

_BWD_FILTER_ALGOS = [
    "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_0",
    # non-deterministic
    "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_1",
    "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_FFT",
    "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_3",
    # non-deterministic, algo0 with workspaceS
    "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_WINOGRAD",
    # not implemented
    "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_WINOGRAD_NONFUSED",
    "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_FFT_TILING",
    "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_COUNT",
]

_BWD_DATA_ALGOS = [
    "CUDNN_CONVOLUTION_BWD_DATA_ALGO_0",
    # non-deterministic
    "CUDNN_CONVOLUTION_BWD_DATA_ALGO_1",
    "CUDNN_CONVOLUTION_BWD_DATA_ALGO_FFT",
    "CUDNN_CONVOLUTION_BWD_DATA_ALGO_FFT_TILING",
    "CUDNN_CONVOLUTION_BWD_DATA_ALGO_WINOGRAD",
    "CUDNN_CONVOLUTION_BWD_DATA_ALGO_WINOGRAD_NONFUSED",
    "CUDNN_CONVOLUTION_BWD_DATA_ALGO_COUNT",
]

_ALGO_TYPE = [
    "fwd",
    "bwd_filter",
    "bwd_data"
]


def algo_to_index(algo_type, algo_name):
    """Return a index represents the algorithm, which can be used in
    calling CuDNN function

    Parameters
    ----------
        algo_type : str
            ["fwd", "bwd_filter", "bwd_data]

        algo_name : str
            algorithm name in cudnn definition
            fwd = [
                "CUDNN_CONVOLUTION_FWD_ALGO_IMPLICIT_GEMM",
                "CUDNN_CONVOLUTION_FWD_ALGO_IMPLICIT_PRECOMP_GEMM",
                "CUDNN_CONVOLUTION_FWD_ALGO_GEMM",
                "CUDNN_CONVOLUTION_FWD_ALGO_DIRECT",
                "CUDNN_CONVOLUTION_FWD_ALGO_FFT",
                "CUDNN_CONVOLUTION_FWD_ALGO_FFT_TILING",
                "CUDNN_CONVOLUTION_FWD_ALGO_WINOGRAD",
                "CUDNN_CONVOLUTION_FWD_ALGO_WINOGRAD_NONFUSED",
                "CUDNN_CONVOLUTION_FWD_ALGO_COUNT",
            ]
            bwd_filter = [
                "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_0",
                # non-deterministic
                "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_1",
                "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_FFT",
                "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_3",
                # non-deterministic, algo0 with workspaceS
                "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_WINOGRAD",
                # not implemented
                "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_WINOGRAD_NONFUSED",
                "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_FFT_TILING",
                "CUDNN_CONVOLUTION_BWD_FILTER_ALGO_COUNT",
            ]
            bwd_data = [
                "CUDNN_CONVOLUTION_BWD_DATA_ALGO_0",
                # non-deterministic
                "CUDNN_CONVOLUTION_BWD_DATA_ALGO_1",
                "CUDNN_CONVOLUTION_BWD_DATA_ALGO_FFT",
                "CUDNN_CONVOLUTION_BWD_DATA_ALGO_FFT_TILING",
                "CUDNN_CONVOLUTION_BWD_DATA_ALGO_WINOGRAD",
                "CUDNN_CONVOLUTION_BWD_DATA_ALGO_WINOGRAD_NONFUSED",
                "CUDNN_CONVOLUTION_BWD_DATA_ALGO_COUNT",
            ]

    Returns
    -------
        algo: int
            algorithm index

    """
    idx = -1
    if algo_type == "fwd":
        idx = _FWD_ALGOS.index(algo_name)
    elif algo_type == "bwd_filter":
        idx = _BWD_FILTER_ALGOS.index(algo_name)
    elif algo_type == "bwd_data":
        idx = _BWD_DATA_ALGOS.index(algo_name)
    assert idx >= 0
    return idx


def _get_np_int32_array_handle(arr):
    """Return a void_p handle for a numpy array

    Parameters
    ----------
    arr: numpy.NDArray
        source numpy array

    Returns
    -------
    ptr:  ctypes.c_void_p
        pointer to the data
    """
    assert arr.dtype == np.int32
    ptr = arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
    return ctypes.cast(ptr, ctypes.c_void_p)

def _prepare_global_func_params(dims,
                                pad,
                                stride,
                                dilation,
                                x_shape=None,
                                w_shape=None):
    full_dims = dims + 2
    if x_shape:
        assert isinstance(x_shape, list)
        assert len(x_shape) == full_dims
    if w_shape:
        assert isinstance(w_shape, list)
        assert len(w_shape) == full_dims

    pad = np.full(dims, pad, dtype=np.int32) if isinstance(pad, int) \
        else np.array(pad, dtype=np.int32)
    stride = np.full(dims, stride, dtype=np.int32) if isinstance(stride, int) \
        else np.array(stride, dtype=np.int32)
    dilation = np.full(dims, dilation, dtype=np.int32) if isinstance(dilation, int) \
        else np.array(dilation, dtype=np.int32)

    xshape = np.array(x_shape, dtype=np.int32) if x_shape else None
    wshape = np.array(w_shape, dtype=np.int32) if x_shape else None

    return pad, stride, dilation, xshape, wshape


def conv_output_shape(tensor_format,
                      pad,
                      stride,
                      dilation,
                      x_shape,
                      w_shape,
                      data_dtype,
                      conv_dtype):
    """Get output shape of 2D or 3D convolution

    Paramters
    ---------
    tensor_format: int
        0: CUDNN_TENSOR_NCHW
        1: CUDNN_TENSOR_NHWC
        2: CUDNN_TENSOR_NCHW_VECT_C
    pad: int or list
        padding
    stride: int or list
        stride
    dilation: int or list
        dilation
    x_shape: list
        input shape
    w_shape: list
        weight shape
    data_dtype: str
        data type
    conv_dtype: str
        convolution type

    Returns
    -------
    oshape: list
        output shape
    """
    dims = len(x_shape)
    assert dims in (4, 5)

    pad, stride, dilation, xshape, wshape = \
        _prepare_global_func_params(dims - 2, pad, stride, dilation, x_shape, w_shape)
    oshape = np.zeros((dims), dtype=np.int32)

    func = tvm._ffi.get_global_func("tvm.contrib.cudnn.conv.output_shape")
    func(tensor_format,
         dims - 2,
         _get_np_int32_array_handle(pad),
         _get_np_int32_array_handle(stride),
         _get_np_int32_array_handle(dilation),
         _get_np_int32_array_handle(xshape),
         _get_np_int32_array_handle(wshape),
         _get_np_int32_array_handle(oshape),
         data_dtype,
         conv_dtype)
    return list(oshape)


def conv_find_algo(tensor_format,
                   pad,
                   stride,
                   dilation,
                   x_shape,
                   w_shape,
                   y_shape,
                   data_dtype,
                   conv_dtype):
    """Choose the best algo for the given input.

    Paramters
    ---------
    tensor_format: int
        0: CUDNN_TENSOR_NCHW
        1: CUDNN_TENSOR_NHWC
        2: CUDNN_TENSOR_NCHW_VECT_C
    pad: int or list
        padding
    stride: int or list
        stride
    dilation: int or list
        dilation
    x_shape: list
        input shape
    w_shape: list
        weight shape
    y_shape: list
        output shape
    data_dtype: str
        data type
    conv_dtype: str
        convolution type

    Returns
    -------
    algo: int
        algo chosen by CUDNN
    """
    dims = len(x_shape)
    assert dims in (4, 5)

    pad, stride, dilation, xshape, wshape = \
        _prepare_global_func_params(dims - 2, pad, stride, dilation, x_shape, w_shape)
    yshape = np.array(y_shape, dtype=np.int32)
    func = tvm._ffi.get_global_func("tvm.contrib.cudnn.conv.find_algo")
    return func(tensor_format,
                dims - 2,
                _get_np_int32_array_handle(pad),
                _get_np_int32_array_handle(stride),
                _get_np_int32_array_handle(dilation),
                _get_np_int32_array_handle(xshape),
                _get_np_int32_array_handle(wshape),
                _get_np_int32_array_handle(yshape),
                data_dtype,
                conv_dtype)


def conv_forward(x,
                 w,
                 pad,
                 stride,
                 dilation,
                 conv_mode,
                 tensor_format,
                 algo,
                 conv_dtype):
    """Create an extern op that compute 2D or 3D convolution with CuDNN

    Parameters
    ----------
    x: Tensor
        input feature map
    w: Tensor
        convolution weight
    pad: int or list
        padding
    stride: int or list
        stride
    dilation: int or list
        dilation
    conv_mode: int
        0: CUDNN_CONVOLUTION
        1: CUDNN_CROSS_CORRELATION
    tensor_format: int
        0: CUDNN_TENSOR_NCHW
        1: CUDNN_TENSOR_NHWC
        2: CUDNN_TENSOR_NCHW_VECT_C
    algo: int
        Forward algorithm, get index from ```algo_to_index``` function
        if algo == -1, the best algo will be chosen by CUDNN
    conv_dtype: str
        convolution type

    Returns
    -------
    y: Tensor
        The result tensor
    """
    dims = len(x.shape)
    assert dims in (4, 5)

    conv_dtype = x.dtype if conv_dtype is None else conv_dtype
    pad, stride, dilation, _, _ = \
        _prepare_global_func_params(dims - 2, pad, stride, dilation)

    oshape = conv_output_shape(tensor_format,
                               pad,
                               stride,
                               dilation,
                               list(x.shape),
                               list(w.shape),
                               x.dtype,
                               conv_dtype)
    if algo == -1:
        # For now if we try to call `cudnnFindConvolutionForwardAlgorithm` when
        # using INT8 data type, CuDNN will crash down.
        # On the other hand, CuDNN only support IMPLICIT_PRECOMP_GEMM at NHWC format
        if tensor_format == 1 and conv_dtype == "int32":
            algo = 1
        else:
            algo = conv_find_algo(tensor_format,
                                  pad,
                                  stride,
                                  dilation,
                                  list(x.shape),
                                  list(w.shape),
                                  oshape,
                                  x.dtype,
                                  conv_dtype)

    if dims == 4:
        return te.extern(
            oshape, [x, w],
            lambda ins, outs: tvm.tir.call_packed(
                "tvm.contrib.cudnn.conv2d.forward",
                conv_mode,
                tensor_format,
                algo,
                pad[0],
                pad[1],
                stride[0],
                stride[1],
                dilation[0],
                dilation[1],
                ins[0],
                ins[1],
                outs[0],
                conv_dtype), name="y")

    return te.extern(
        oshape, [x, w],
        lambda ins, outs: tvm.tir.call_packed(
            "tvm.contrib.cudnn.conv3d.forward",
            conv_mode,
            tensor_format,
            algo,
            pad[0],
            pad[1],
            pad[2],
            stride[0],
            stride[1],
            stride[2],
            dilation[0],
            dilation[1],
            dilation[2],
            ins[0],
            ins[1],
            outs[0],
            conv_dtype), name="y")

def grouped_conv2d_w_shape(group_count,
                   in_channel,
                   out_channel,
                   filter_h,
                   filter_w):
    """Get weight shape for a 2D grouped convolution

    Parameters
    ----------
    group_count: int
        group count
    in_channel: int
        input channel
    out_channel: int
        output channel
    filter_h: int
        filter height
    filter_w: int
        filter width

    Returns
    -------
    wshape: list
        weight shape
    """
    return [out_channel, int(in_channel / group_count), filter_h, filter_w]

def grouped_conv2d_output_shape(tensor_format,
                                group_count,
                                pad_h,
                                pad_w,
                                stride_h,
                                stride_w,
                                dilation_h,
                                dilation_w,
                                x_shape,
                                w_shape):
    """Get output shape of 2D grouped, convolution

    Paramters
    ---------
    tensor_format: int
        0: CUDNN_TENSOR_NCHW
        1: CUDNN_TENSOR_NHWC
        2: CUDNN_TENSOR_NCHW_VECT_C
    group_count: int
        group count
    pad_h: int
        height pad
    pad_w: int
        weight pad
    stride_h: int
        height stride
    stride_w: int
        width stride
    dilation_h: int
        height dilation
    dilation_w: int
        width dilation
    x_shape: list
        input shape
    w_shape: list
        weight shape

    Returns
    -------
    oshape: list
        output shape
    """
    assert isinstance(x_shape, list)
    assert isinstance(w_shape, list)
    assert len(x_shape) == 4
    assert len(w_shape) == 4
    oshape = np.zeros((len(x_shape)), dtype=np.int32)
    func = _get_global_func("tvm.contrib.cudnn.grouped_conv2d.output_shape")
    func(tensor_format,
         group_count,
         pad_h,
         pad_w,
         stride_h,
         stride_w,
         dilation_h,
         dilation_w,
         x_shape[0].value,
         x_shape[1].value,
         x_shape[2].value,
         x_shape[3].value,
         w_shape[0].value,
         w_shape[1].value,
         w_shape[2].value,
         w_shape[3].value,
         _get_np_int32_array_handle(oshape))
    return list(oshape)


def grouped_conv2d_find_algo(tensor_format,
                             group_count,
                             pad_h,
                             pad_w,
                             stride_h,
                             stride_w,
                             dilation_h,
                             dilation_w,
                             x_shape,
                             w_shape,
                             y_shape):
    """Choose the best algo for the given input.

    Paramters
    ---------
    tensor_format: int
        0: CUDNN_TENSOR_NCHW
        1: CUDNN_TENSOR_NHWC
        2: CUDNN_TENSOR_NCHW_VECT_C
    group_count: int
        group count
    pad_h: int
        height pad
    pad_w: int
        weight pad
    stride_h: int
        height stride
    stride_w: int
        width stride
    dilation_h: int
        height dilation
    dilation_w: int
        width dilation
    x_shape: list
        input shape
    w_shape: list
        weight shape
    y_shape: list
        output shape

    Returns
    -------
    algo: int
        algo chosen by CUDNN
    """
    func = _get_global_func("tvm.contrib.cudnn.grouped_conv2d.find_algo")
    return func(tensor_format,
                group_count,
                pad_h,
                pad_w,
                stride_h,
                stride_w,
                dilation_h,
                dilation_w,
                x_shape[0].value,
                x_shape[1].value,
                x_shape[2].value,
                x_shape[3].value,
                w_shape[0].value,
                w_shape[1].value,
                w_shape[2].value,
                w_shape[3].value,
                int(y_shape[0]),
                int(y_shape[1]),
                int(y_shape[2]),
                int(y_shape[3]))


def grouped_conv2d_forward(x,
                           w,
                           group_count,
                           stride_h=1,
                           stride_w=1,
                           pad_h=0,
                           pad_w=0,
                           dilation_h=1,
                           dilation_w=1,
                           conv_mode=1,
                           tensor_format=0,
                           algo=-1):
    """Create an extern op that compute 2D convolution with CuDNN

    Parameters
    ----------
    x: Tensor
        input feature map
    w: Tensor
        convolution weight
    group_count: int
        group count
    stride_h: int
        height stride
    stride_w: int
        width stride
    pad_h: int
        height pad
    pad_w: int
        weight pad
    dilation_h: int
        height dilation
    dilation_w: int
        width dilation
    conv_mode: int
        0: CUDNN_CONVOLUTION
        1: CUDNN_CROSS_CORRELATION
    tensor_format: int
        0: CUDNN_TENSOR_NCHW
        1: CUDNN_TENSOR_NHWC
        2: CUDNN_TENSOR_NCHW_VECT_C
    algo: int
        Forward algorithm, get index from ```algo_to_index``` function
        if algo == -1, the best algo will be chosen by CUDNN

    Returns
    -------
    y: Tensor
        The result tensor
    """
    oshape = grouped_conv2d_output_shape(tensor_format,
                                         group_count,
                                         pad_h,
                                         pad_w,
                                         stride_h,
                                         stride_w,
                                         dilation_h,
                                         dilation_w,
                                         list(x.shape),
                                         list(w.shape))
    if algo == -1:
        algo = grouped_conv2d_find_algo(tensor_format,
                                        group_count,
                                        pad_h,
                                        pad_w,
                                        stride_h,
                                        stride_w,
                                        dilation_h,
                                        dilation_w,
                                        list(x.shape),
                                        list(w.shape),
                                        oshape)

    return _api.extern(
        oshape, [x, w],
        lambda ins, outs: _intrin.call_packed(
            "tvm.contrib.cudnn.grouped_conv2d.forward",
            conv_mode,
            tensor_format,
            algo,
            group_count,
            pad_h,
            pad_w,
            stride_h,
            stride_w,
            dilation_h,
            dilation_w,
            ins[0],
            ins[1],
            outs[0]), name="y")
