"""Tests for select_and_freeze_root_refs.

Each test maps to a wiki fail case or invariant from Spec A. Run:

    pytest tests/test_node_selection.py -v
"""

import pickle

import pytest
from omegaconf import OmegaConf

from flexlock.exceptions import UnresolvedInterpolationError
from flexlock.utils import select_and_freeze_root_refs


# --- Invariants ---

def test_no_key_returns_root_unchanged():
    cfg = OmegaConf.create({"a": 1, "b": 2})
    assert select_and_freeze_root_refs(cfg, None) is cfg


def test_missing_key_raises():
    cfg = OmegaConf.create({"a": 1})
    with pytest.raises(KeyError):
        select_and_freeze_root_refs(cfg, "nonexistent")


def test_simple_key_lookup():
    cfg = OmegaConf.create({"train": {"lr": 0.01}})
    result = select_and_freeze_root_refs(cfg, "train")
    assert result.lr == 0.01


# --- Wiki fail cases ---

def test_root_ref_resolved_at_selection():
    """Wiki 2026-05-30: InterpolationKeyError on ${preprocess_dir} after proj.get('encode_val')."""
    cfg = OmegaConf.create({
        "preprocess_dir": "outputs/preprocess/s4",
        "encode_val": {
            "data_dir": "${preprocess_dir}",
            "save_dir": "outputs/encode",
        },
    })
    sub = select_and_freeze_root_refs(cfg, "encode_val")
    container = OmegaConf.to_container(sub, resolve=True)
    assert container["data_dir"] == "outputs/preprocess/s4"


def test_save_dir_root_interpolation():
    """Wiki 2026-05-30: cfg.save_dir = ${pipeline_dir}/train fails when -s train detaches."""
    cfg = OmegaConf.create({
        "pipeline_dir": "outputs/pipeline_1",
        "train": {"save_dir": "${pipeline_dir}/train"},
    })
    sub = select_and_freeze_root_refs(cfg, "train")
    container = OmegaConf.to_container(sub, resolve=True)
    assert container["save_dir"] == "outputs/pipeline_1/train"


def test_main_save_dir_sweep():
    """Wiki gotcha: ${main.save_dir} in nested sub-config doesn't track per-item save_dir.

    After freezing, the cross-tree reference is gone, so per-item overrides
    of save_dir take effect cleanly downstream.
    """
    cfg = OmegaConf.create({
        "main": {"save_dir": "outputs/main"},
        "train": {
            "save_dir": "${main.save_dir}",
            "log_dir": "${main.save_dir}/logs",
        },
    })
    sub = select_and_freeze_root_refs(cfg, "train")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["save_dir"] == "outputs/main"
    assert raw["log_dir"] == "outputs/main/logs"


# --- Resolver preservation ---

def test_vinc_resolver_preserved():
    """${vinc:...} resolver calls survive selection unchanged."""
    cfg = OmegaConf.create({"stage": {"save_dir": "${vinc:outputs/run}"}})
    sub = select_and_freeze_root_refs(cfg, "stage")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["save_dir"] == "${vinc:outputs/run}"


def test_latest_resolver_preserved():
    cfg = OmegaConf.create({"stage": {"data_dir": "${latest:outputs/run_*}"}})
    sub = select_and_freeze_root_refs(cfg, "stage")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["data_dir"] == "${latest:outputs/run_*}"


def test_run_lock_with_nested_root_ref():
    """${run_lock:${cnf_run_dir},config.save_dir} — outer preserved, inner frozen.

    The inner ${cnf_run_dir} is a root-scope simple ref → freeze. The outer
    ${run_lock:...,...} is a resolver call → preserve.
    """
    cfg = OmegaConf.create({
        "cnf_run_dir": "outputs/cnf/run_0001",
        "stage": {"model_dir": "${run_lock:${cnf_run_dir},config.save_dir}"},
    })
    sub = select_and_freeze_root_refs(cfg, "stage")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["model_dir"] == "${run_lock:outputs/cnf/run_0001,config.save_dir}"


def test_chained_ref_to_resolver():
    """${cnf_run_dir} at root, value is ${vinc:...}. Sub-node ref to cnf_run_dir
    substitutes the unresolved string verbatim so vinc still fires at submit time."""
    cfg = OmegaConf.create({
        "cnf_run_dir": "${vinc:outputs/cnf/run}",
        "stage": {"data_dir": "${cnf_run_dir}"},
    })
    sub = select_and_freeze_root_refs(cfg, "stage")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["data_dir"] == "${vinc:outputs/cnf/run}"


# --- Intra-sub-tree preservation ---

def test_intra_sub_tree_refs_preserved():
    cfg = OmegaConf.create({
        "stage": {
            "save_dir": "outputs/stage",
            "logs": "${save_dir}/logs",
        }
    })
    sub = select_and_freeze_root_refs(cfg, "stage")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["logs"] == "${save_dir}/logs"
    container = OmegaConf.to_container(sub, resolve=True)
    assert container["logs"] == "outputs/stage/logs"


def test_relative_interp_preserved():
    """OmegaConf relative refs (`${...key}`) navigate from the access site and
    can't be statically frozen — the freeze pass must pass them through."""
    cfg = OmegaConf.create({
        "train": {
            "input_path": "data/train.csv",
            "_snapshot_": {"data": {"main": "${...input_path}"}},
        }
    })
    sub = select_and_freeze_root_refs(cfg, "train")
    # Raw form preserved
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["_snapshot_"]["data"]["main"] == "${...input_path}"
    # Still resolves correctly when fully materialized via the root cfg
    cfg.train = sub  # type: ignore[attr-defined]
    resolved = OmegaConf.to_container(cfg.train, resolve=True)
    assert resolved["_snapshot_"]["data"]["main"] == "data/train.csv"


def test_relative_interp_embedded_in_string_preserved():
    """A `${..key}` embedded in a larger string (e.g. `${..save_dir}/logs`)
    must also be preserved verbatim."""
    cfg = OmegaConf.create({
        "stage": {
            "save_dir": "outputs/stage",
            "inner": {"logs": "${..save_dir}/logs"},
        }
    })
    sub = select_and_freeze_root_refs(cfg, "stage")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["inner"]["logs"] == "${..save_dir}/logs"


def test_dotted_intra_ref_preserved():
    cfg = OmegaConf.create({
        "stage": {
            "inner": {"value": 42},
            "ref": "${inner.value}",
        }
    })
    sub = select_and_freeze_root_refs(cfg, "stage")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["ref"] == "${inner.value}"


# --- Type preservation ---

def test_primitive_type_preserved_through_freeze():
    """${batch_size} at root, batch_size: 64 → sub-node leaf becomes int 64, not str."""
    cfg = OmegaConf.create({
        "batch_size": 64,
        "stage": {"bs": "${batch_size}"},
    })
    sub = select_and_freeze_root_refs(cfg, "stage")
    assert sub.bs == 64
    assert isinstance(sub.bs, int)


# --- Robustness ---

def test_pickle_roundtrip():
    """A frozen sub-node must pickle and unpickle without losing meaning.

    This is the failure mode for HPC submission: cloudpickle drops the parent
    pointer, and previously detached refs failed at the worker.
    """
    cfg = OmegaConf.create({
        "anchor": "outputs/x",
        "stage": {"data_dir": "${anchor}", "save_dir": "outputs/stage"},
    })
    sub = select_and_freeze_root_refs(cfg, "stage")
    restored = pickle.loads(pickle.dumps(sub))
    container = OmegaConf.to_container(restored, resolve=True)
    assert container["data_dir"] == "outputs/x"


def test_idempotent():
    """Selecting twice produces an equivalent config."""
    cfg = OmegaConf.create({
        "anchor": "outputs/x",
        "stage": {"data_dir": "${anchor}", "save_dir": "outputs/stage"},
    })
    sub1 = select_and_freeze_root_refs(cfg, "stage")
    wrapped = OmegaConf.create({"stage": OmegaConf.to_container(sub1, resolve=False)})
    sub2 = select_and_freeze_root_refs(wrapped, "stage")
    assert OmegaConf.to_container(sub1, resolve=False) == OmegaConf.to_container(
        sub2, resolve=False
    )


def test_unresolved_root_ref_errors_clearly():
    cfg = OmegaConf.create({"stage": {"data_dir": "${nonexistent}"}})
    with pytest.raises(UnresolvedInterpolationError, match="nonexistent"):
        select_and_freeze_root_refs(cfg, "stage")


def test_unresolved_dotted_ref_errors_clearly():
    cfg = OmegaConf.create({"stage": {"data_dir": "${some.deep.path}"}})
    with pytest.raises(UnresolvedInterpolationError, match="some"):
        select_and_freeze_root_refs(cfg, "stage")


def test_embedded_interpolation_in_string():
    """${anchor} embedded mid-string, not whole-string."""
    cfg = OmegaConf.create({
        "anchor": "data",
        "stage": {"path": "prefix/${anchor}/suffix"},
    })
    sub = select_and_freeze_root_refs(cfg, "stage")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["path"] == "prefix/data/suffix"


def test_multiple_interpolations_in_string():
    cfg = OmegaConf.create({
        "a": "alpha",
        "b": "beta",
        "stage": {"composed": "${a}-${b}"},
    })
    sub = select_and_freeze_root_refs(cfg, "stage")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["composed"] == "alpha-beta"


def test_list_values_walked():
    cfg = OmegaConf.create({
        "anchor": "outputs/x",
        "stage": {"paths": ["${anchor}/a", "${anchor}/b"]},
    })
    sub = select_and_freeze_root_refs(cfg, "stage")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["paths"] == ["outputs/x/a", "outputs/x/b"]


def test_chained_save_dir_via_pipeline_dir():
    """extract.save_dir = ${pipeline_dir}/features where pipeline_dir = ${save_dir}.

    The freeze must follow the two-hop chain pipeline_dir → save_dir → concrete
    and produce a concrete path, not ${save_dir}/features which becomes
    self-referential in the detached config.

    Regression: _submit_sweep raised InterpolationResolutionError on
    OmegaConf.to_container(sweep_cfg, resolve=True) because the freeze stopped
    at the first hop, substituting ${pipeline_dir} with ${save_dir} verbatim.
    """
    cfg = OmegaConf.create({
        "save_dir": "outputs/colloc_run",
        "pipeline_dir": "${save_dir}",
        "extract": {
            "save_dir": "${pipeline_dir}/features",
            "cols": ["longitude"],
        },
    })
    sub = select_and_freeze_root_refs(cfg, "extract")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["save_dir"] == "outputs/colloc_run/features"
    container = OmegaConf.to_container(sub, resolve=True)
    assert container["save_dir"] == "outputs/colloc_run/features"


def test_self_referential_save_dir_frozen_from_root():
    """save_dir: ${save_dir}/features — sub-config's own save_dir shadows the
    root ref, creating a circular interpolation at resolution time.

    select_and_freeze_root_refs must detect that the sub-tree value for
    save_dir is itself a string containing ${save_dir} and fall through to
    the root lookup, producing a concrete path rather than a self-reference.

    Regression: this pattern caused InterpolationResolutionError when
    _submit_sweep called OmegaConf.to_container(sweep_cfg, resolve=True).
    """
    cfg = OmegaConf.create({
        "save_dir": "outputs/colloc_run",
        "extract": {
            "save_dir": "${save_dir}/features",
            "cols": ["longitude", "latitude"],
        },
    })
    sub = select_and_freeze_root_refs(cfg, "extract")
    # Raw form should already be concrete — no interpolation left
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["save_dir"] == "outputs/colloc_run/features"
    # Full resolution must not raise InterpolationResolutionError
    container = OmegaConf.to_container(sub, resolve=True)
    assert container["save_dir"] == "outputs/colloc_run/features"
    assert container["cols"] == ["longitude", "latitude"]


def test_nested_dict_walked():
    cfg = OmegaConf.create({
        "anchor": "outputs/x",
        "stage": {
            "datamodule": {"path": "${anchor}"},
            "trainer": {"logger": {"dir": "${anchor}/logs"}},
        },
    })
    sub = select_and_freeze_root_refs(cfg, "stage")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["datamodule"]["path"] == "outputs/x"
    assert raw["trainer"]["logger"]["dir"] == "outputs/x/logs"


def test_two_hop_mixed_string_ref():
    """Regression: ${split.save_dir}/train.txt where split.save_dir = ${pipeline_dir}/split.

    The freeze must fully resolve the two-hop chain — concrete pipeline_dir →
    mixed-string split.save_dir → embedded reference in prepare.listing_path —
    and produce a concrete path in the frozen sub-config.

    Bug: _resolve_in_root("split.save_dir") encountered "${pipeline_dir}/split"
    (a mixed string, not whole-string), so _whole_string_interp returned None and
    the chain stopped.  _process_one_interp then embedded the raw string verbatim,
    leaving "${pipeline_dir}/split/train.txt" in the frozen config, which raised
    InterpolationKeyError at snapshot time because pipeline_dir is absent from the
    detached sub-config scope.
    """
    cfg = OmegaConf.create({
        "pipeline_dir": "outputs/data_pipeline_0004",
        "split": {
            "save_dir": "${pipeline_dir}/split",
        },
        "prepare": {
            "listing_path": "${split.save_dir}/train.txt",
        },
    })
    sub = select_and_freeze_root_refs(cfg, "prepare")
    raw = OmegaConf.to_container(sub, resolve=False)
    assert raw["listing_path"] == "outputs/data_pipeline_0004/split/train.txt"
    container = OmegaConf.to_container(sub, resolve=True)
    assert container["listing_path"] == "outputs/data_pipeline_0004/split/train.txt"
