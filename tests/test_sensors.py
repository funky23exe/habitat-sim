#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import itertools
import json
import os.path as osp

import numpy as np
import pytest
import quaternion

import habitat_sim
import habitat_sim.errors
from examples.settings import make_cfg
from habitat_sim.utils.common import quat_from_coeffs

_test_scenes = [
    osp.abspath(
        osp.join(
            osp.dirname(__file__),
            "../data/scene_datasets/mp3d/17DRP5sb8fy/17DRP5sb8fy.glb",
        )
    ),
    osp.abspath(
        osp.join(
            osp.dirname(__file__),
            "../data/scene_datasets/habitat-test-scenes/skokloster-castle.glb",
        )
    ),
    osp.abspath(
        osp.join(
            osp.dirname(__file__),
            "../data/scene_datasets/habitat-test-scenes/van-gogh-room.glb",
        )
    ),
]


@pytest.mark.gfxtest
@pytest.mark.parametrize(
    "scene,has_sem,sensor_type,gpu2gpu",
    list(
        itertools.product(
            _test_scenes[0:1],
            [True],
            ["color_sensor", "depth_sensor", "semantic_sensor"],
            [True, False],
        )
    )
    + list(
        itertools.product(
            _test_scenes[1:], [False], ["color_sensor", "depth_sensor"], [True, False]
        )
    ),
)
def test_sensors(scene, has_sem, sensor_type, gpu2gpu, sim, make_cfg_settings):
    if not osp.exists(scene):
        pytest.skip("Skipping {}".format(scene))

    if not habitat_sim.cuda_enabled and gpu2gpu:
        pytest.skip("Skipping GPU->GPU test")

    make_cfg_settings = {k: v for k, v in make_cfg_settings.items()}
    make_cfg_settings["semantic_sensor"] = has_sem
    make_cfg_settings["scene"] = scene

    cfg = make_cfg(make_cfg_settings)
    for sensor_spec in cfg.agents[0].sensor_specifications:
        sensor_spec.gpu2gpu_transfer = gpu2gpu

    sim.reconfigure(cfg)
    with open(
        osp.abspath(
            osp.join(
                osp.dirname(__file__),
                "gt_data",
                "{}-state.json".format(osp.basename(osp.splitext(scene)[0])),
            )
        ),
        "r",
    ) as f:
        render_state = json.load(f)
        state = habitat_sim.AgentState()
        state.position = render_state["pos"]
        state.rotation = quat_from_coeffs(render_state["rot"])

    sim.initialize_agent(0, state)
    obs = sim.step("move_forward")

    assert sensor_type in obs, f"{sensor_type} not in obs"

    gt = np.load(
        osp.abspath(
            osp.join(
                osp.dirname(__file__),
                "gt_data",
                "{}-{}.npy".format(osp.basename(osp.splitext(scene)[0]), sensor_type),
            )
        )
    )
    if gpu2gpu:
        import torch

        for k, v in obs.items():
            if torch.is_tensor(v):
                obs[k] = v.cpu().numpy()

    # Different GPUs and different driver version will produce slightly different images
    assert np.linalg.norm(
        obs[sensor_type].astype(np.float) - gt.astype(np.float)
    ) < 1.5e-2 * np.linalg.norm(gt.astype(np.float)), f"Incorrect {sensor_type} output"


# Tests to make sure that no sensors is supported and doesn't crash
# Also tests to make sure we can have multiple instances
# of the simulator with no sensors
def test_smoke_no_sensors(make_cfg_settings):
    sims = []
    for scene in _test_scenes:
        if not osp.exists(scene):
            continue

        make_cfg_settings = {k: v for k, v in make_cfg_settings.items()}
        make_cfg_settings["semantic_sensor"] = False
        make_cfg_settings["scene"] = scene
        cfg = make_cfg(make_cfg_settings)
        cfg.agents[0].sensor_specifications = []
        sims.append(habitat_sim.Simulator(cfg))
