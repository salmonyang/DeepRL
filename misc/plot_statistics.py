#!/usr/bin/env python
# -*- coding: utf8 -*-

import os
import numpy as np
import json
import argparse
from utils import ge_1
import re
import operator
from tensorflow.python.summary.event_multiplexer import EventMultiplexer
from Exceptions import WrongArgumentsError

import matplotlib
gui_env = ['TKAgg', 'GTKAgg', 'Qt4Agg', 'WXAgg', 'agg']
for gui in gui_env:
    try:
        matplotlib.use(gui, warn=False, force=True)
        from matplotlib import pyplot as plt
        break
    except ImportError:
        continue

# Source: http://stackoverflow.com/questions/14313510/how-to-calculate-moving-average-using-numpy
def moving_average(a, n):
    """Compute the moving average of an array a of numbers using a window length n."""
    ret = np.cumsum(a, dtype=float)
    ret[n:] = ret[n:] - ret[:-n]
    return ret[n - 1:] / n

# Source: https://github.com/tensorflow/tensorflow/blob/d413f62fba038d820b775d95ddd518fb6f43d3ed/tensorflow/tensorboard/components/vz_line_chart/vz-line-chart.ts#L432
def exponential_smoothing(a, weight):
    factor = (pow(1000, weight) - 1) / 999
    length = len(a)
    kernelRadius = np.floor(length * factor / 2)
    result = []
    for i, x in enumerate(a):
        actualKernelRadius = min(kernelRadius, i)
        start = int(i - actualKernelRadius)
        end = int(i + actualKernelRadius + 1)
        if end >= length:
            result.append(np.inf)
        elif x == np.inf:
            result.append(x)
        else:
            result.append(np.mean(list(filter(lambda x: x != np.inf, a[start:end]))))
    return result

def create_smoother(f, *args):
    return lambda x: f(x, *args)

def plot(x, y, x_label, scalar, xmax=None, ymin=None, ymax=None):
    x_label_upper = x_label[0].upper() + x_label[1:]
    fig = plt.figure()
    plt.plot(x, y)
    plt.xlim(xmax=xmax)
    plt.ylim(ymin=ymin, ymax=ymax)
    plt.xlabel(x_label_upper)
    plt.ylabel(scalar)
    plt.title("{} per {}".format(scalar, x_label))
    fig.canvas.set_window_title("{} per {}".format(scalar, x_label))

def plot_tasks(data, x_label, smoothing_function=None, xmax=None):
    x_label_upper = x_label[0].upper() + x_label[1:]
    for scalar, tasks in data.items():
        fig = plt.figure()
        # min_y = np.inf
        # max_y = -np.inf
        for task, epochs_values in sorted(tasks.items(), key=operator.itemgetter(0)):
            mean = np.mean(epochs_values["values"], axis=0)
            if smoothing_function:
                mean = smoothing_function(mean)
            # percentiles = np.percentile(epochs_values["values"], [25, 75], axis=0)
            std = np.std(epochs_values["values"], axis=0)
            std = std[len(std) - len(mean):]
            # error_min, error_max = mean - std, mean + std
            plt.plot(epochs_values["epochs"], mean, label="Task " + str(task))
            # plt.fill_between(x, error_min, error_max, alpha=0.3)
            # min_y = min(min_y, min(error_min))
            # max_y = max(max_y, max(filter(lambda x: x != np.inf, error_max)))
        plt.legend()
        plt.xlim(xmax=xmax)
        # plt.ylim(ymin=min(0, min_y), ymax=max(0, max_y + 0.1 * max_y))
        plt.ylim(ymin=0)
        plt.xlabel(x_label_upper)
        plt.ylabel(scalar)
        plt.title("{} per {}".format(scalar, x_label))
        fig.canvas.set_window_title("{} per {}".format(scalar, x_label))
    plt.show()

def plot_tf_monitor_stats(stats_path, xmax=None, smoothing_function=None):
    f = open(stats_path)
    contents = json.load(f)
    data = contents["episode_rewards"]
    if smoothing_function:
        data = smoothing_function(data)
    min_aer = min(data)
    max_aer = max(filter(lambda x: x != np.inf, data))
    ymin = min(0, min_aer)
    ymax = max(0, max_aer + 0.1 * max_aer)
    plot(range(len(data)), data, "episode", "total reward", xmax=xmax, ymin=ymin, ymax=ymax)

    data = contents["episode_lengths"]
    if smoothing_function:
        data = smoothing_function(data)
    max_ael = max(filter(lambda x: x != np.inf, data))
    ymin = 0
    ymax = (max_ael + 0.1 * max_ael)
    plot(range(len(data)), data, "episode", "length", xmax=xmax, ymin=ymin, ymax=ymax)
    plt.show()

def tf_scalar_data(directory):
    em = EventMultiplexer().AddRunsFromDirectory(directory)
    em.Reload()
    runs = list(em.Runs().keys())
    scalars = em.Runs()[runs[0]]["scalars"]  # Assumes that the scalars of every run are the same

    pattern = re.compile("task(\d+)$")
    data = {}
    for scalar in scalars:
        scalar_data = {}
        for run in runs:
            task = int(pattern.search(run).group(1))
            if task in scalar_data:
                scalar_data[task]["values"].append([x.value for x in em.Scalars(run, scalar)])
            else:
                values = []
                epochs = []
                for s in em.Scalars(run, scalar):
                    values.append(s.value)
                    epochs.append(s.step)
                scalar_data[task] = {
                    "epochs": epochs,
                    "values": [values]
                }
        data[scalar] = scalar_data
    return data

def plot_tf_scalar_summaries(summaries_dir, xmax=None, smoothing_function=None, x_label="episode"):
    data = tf_scalar_data(summaries_dir)
    plot_tasks(data, x_label, smoothing_function=smoothing_function, xmax=xmax)

def plot_tf_scalar_summaries_subdirs(summaries_dir, xmax=None, smoothing_function=None, x_label="episode"):
    _, subdirs, _ = next(os.walk(summaries_dir))

    data = {}
    for subdir in subdirs:
        if not subdir.startswith("exp"):
            continue
        subdir_data = tf_scalar_data(os.path.join(summaries_dir, subdir))
        for scalar, scalar_data in subdir_data.items():
            if scalar not in data:
                data[scalar] = scalar_data
            else:
                for task, epochs_values in scalar_data.items():
                    data[scalar][task]["values"].extend(epochs_values["values"])

    plot_tasks(data, x_label, smoothing_function=smoothing_function, xmax=xmax)

def exp_smoothing_weight_test(value):
    """Require that the weight for exponential smoothing is a weight between 0 and 1"""
    fvalue = float(value)
    if fvalue < 0 or fvalue > 1:
        raise argparse.ArgumentTypeError("{} must be a float between 0 and 1".format(value))
    return fvalue

parser = argparse.ArgumentParser()
parser.add_argument("stats_path", metavar="stats", type=str, help="Path to the Tensorflow monitor stats.json file or summaries directory.")
parser.add_argument("--x_label", type=str, default="episode", choices=["episode", "epoch"], help="Whether to use episode or epoch as x label.")
parser.add_argument("--xmax", type=ge_1, default=None, help="Maximum episode for which to show results.")
parser.add_argument("--exp_smoothing", type=exp_smoothing_weight_test, default=None, help="Use exponential smoothing with a weight 0<=w<=1.")
parser.add_argument("--moving_average", type=ge_1, default=None, help="Use a moving average with a window w>0")
parser.add_argument("--subdirs", action="store_true", default=False, help="Process each subdirectory separately (solves memory issues).")

if __name__ == "__main__":
    args = parser.parse_args()
    if args.exp_smoothing is not None and args.moving_average is not None:
        raise WrongArgumentsError("Maximally 1 smoothing technique can be used.")
    smoothing_technique = None
    if args.exp_smoothing is not None:
        smoothing_technique = create_smoother(exponential_smoothing, args.exp_smoothing)  # args.exp_smoothing holds the weight
    elif args.moving_average is not None:
        smoothing_technique = create_smoother(moving_average, args.moving_average)  # args.moving_average holds the window
    if os.path.isfile(args.stats_path) and args.stats_path.endswith(".json"):
        plot_tf_monitor_stats(args.stats_path, args.xmax, smoothing_technique)
    elif os.path.isdir(args.stats_path):
        if args.subdirs:
            plot_tf_scalar_summaries_subdirs(args.stats_path, args.xmax, smoothing_technique, x_label=args.x_label)
        else:
            plot_tf_scalar_summaries(args.stats_path, args.xmax, smoothing_technique, x_label=args.x_label)
    else:
        raise NotImplementedError("Only a Tensorflow monitor stats.json file or summaries directory is allowed.")
