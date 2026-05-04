"""Train custom hybrid auto-typing models on a user dataset.

End users who want a v9-quality model tuned to their own SWC corpus run
this once, point the auto-typing backend at the resulting model
directory, and from then on all CLI / GUI auto-typing calls use their
custom-trained models.

Expected input dataset layout::

    <data-dir>/
        pyramidal/
            <files>.swc
        interneuron/
            <files>.swc

Subfolder names are the cell-type labels; filenames don't matter. Each
SWC's type column (soma=1, axon=2, basal=3, apical=4) is the per-node
ground truth.

Training stages (run in this order):

    1. Stage 1 cell-type classifier (sklearn ensemble, fast).
    2. Stage 2 per-branch / per-subtree classifier (sklearn ensemble,
       slow — minutes per 1000 cells).
    3. Stage 2b GraphSAGE GNN apical-vs-basal head on the pyramidal
       train split. Always trained as part of the pipeline (torch +
       torch_geometric are required dependencies of the package). Pass
       ``--no-gnn`` if you only want to retrain Stages 1+2 against an
       existing GNN checkpoint.

Output is a directory containing the three standard model files
(``cell_type_classifier.pkl``, ``branch_classifier.pkl``,
``gnn_apical_basal.pt``). Point ``swcstudio`` at this directory by
setting the ``SWCSTUDIO_MODEL_DIR`` environment variable, by passing
``--model-dir`` to the CLI, or by selecting it in the GUI.

Usage from Python::

    from swcstudio.core.auto_typing_train import train_user_models
    train_user_models(
        data_dir="path/to/labeled/dataset",
        output_dir="path/to/save/models",
        train_gnn=True,
    )

Usage from the CLI::

    swcstudio train auto-typing --data-dir path/to/dataset \\
                                --output-dir path/to/save/models
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from swcstudio.core.model_paths import MODEL_FILES


@dataclass
class TrainingResult:
    output_dir: str
    stage1_path: str
    stage2_path: str
    gnn_path: str | None
    stage1_metrics: dict[str, Any]
    stage2_metrics: dict[str, Any]
    gnn_metrics: dict[str, Any] | None


def train_user_models(
    data_dir: str | Path,
    output_dir: str | Path,
    *,
    train_gnn: bool = True,
    seed: int = 42,
    gnn_hidden: int = 128,
    gnn_layers: int = 3,
    gnn_dropout: float = 0.0,
    gnn_epochs: int = 200,
    gnn_patience: int = 25,
) -> TrainingResult:
    """Train Stage 1 + Stage 2 (+ optional GNN) on ``data_dir`` and save
    the resulting model files to ``output_dir``.

    Parameters
    ----------
    data_dir
        Folder with ``pyramidal/`` and ``interneuron/`` subdirectories
        containing labeled SWCs.
    output_dir
        Where to write the trained model files. Created if missing.
    train_gnn
        Whether to retrain the GraphSAGE apical-vs-basal head. Default
        ``True``. Set to ``False`` when you only want to refresh
        Stages 1+2 and re-use the existing bundled GNN checkpoint.
    seed, gnn_hidden, gnn_layers, gnn_dropout, gnn_epochs, gnn_patience
        Hyperparameters. Defaults match the v9 release configuration.

    Returns
    -------
    TrainingResult
        Paths and per-stage metrics. The dict-style metrics are the
        same the underlying training scripts produce so callers can
        log/persist them.
    """
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not (data_dir / "pyramidal").is_dir():
        raise FileNotFoundError(
            f"Expected {data_dir/'pyramidal'} to exist. The dataset "
            "must have one subfolder per cell type."
        )

    print(f"=== Training on {data_dir} -> {output_dir} ===")

    # --- Stage 1 ---
    print("\n[1/3] Training Stage 1 cell-type classifier...")
    from swcstudio.core.auto_typing.train_stage1 import train as train_stage1  # noqa: PLC0415
    stage1_out = output_dir / MODEL_FILES["stage1"]
    stage1_metrics = train_stage1(data_dir, output_path=stage1_out)
    print(f"  saved {stage1_out}")

    # --- Stage 2 ---
    print("\n[2/3] Training Stage 2 per-branch classifier...")
    from swcstudio.core.auto_typing.train_stage2 import train as train_stage2  # noqa: PLC0415
    stage2_out = output_dir / MODEL_FILES["stage2"]
    # train_stage2 builds its own train/test split using seed+test_size;
    # we use the same defaults as the eval pipeline so users can
    # reproduce v9-style numbers if their dataset is large enough.
    stage2_metrics = train_stage2(
        data_dir, output_path=stage2_out, seed=seed,
    )
    print(f"  saved {stage2_out}")

    gnn_out: Path | None = None
    gnn_metrics: dict[str, Any] | None = None
    if train_gnn:
        print("\n[3/3] Training GNN apical-vs-basal head...")
        # torch and torch_geometric are required deps of the package; if
        # they fail to import the install is broken and we want a clear
        # error, not a silent skip.
        import torch  # noqa: PLC0415
        import torch_geometric  # noqa: F401, PLC0415
        from swcstudio.core.auto_typing.gnn_apical_basal import (  # noqa: PLC0415
            ApicalBasalSAGE,
            FeatureScaler,
            TrainConfig,
            cross_validate,
            fit_final,
            load_pyramidal_split,
            save_checkpoint,
        )
        from swcstudio.core.auto_typing.gnn_dataset import DENDRITE_FEATURE_NAMES  # noqa: PLC0415

        cfg = TrainConfig(
            hidden=gnn_hidden,
            n_layers=gnn_layers,
            dropout=gnn_dropout,
            epochs=gnn_epochs,
            patience=gnn_patience,
            seed=seed,
        )
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # The eval split file produced by train_stage2 lives next to
        # the produced bundle. Re-use it so the GNN's test files are
        # the held-out 20% the rest of the pipeline already excluded.
        eval_split_path = stage2_out.parent / "eval_split.json"
        if not eval_split_path.is_file():
            # train_stage2 doesn't always produce an eval_split.json in
            # the user-training flow; fall back to the bundled split
            # next to the auto_typing pipeline modules.
            eval_split_path = (
                Path(__file__).resolve().parent
                / "auto_typing" / "models" / "eval_split.json"
            )

        train_graphs, test_graphs = load_pyramidal_split(
            data_dir, eval_split_path,
            feature_names=DENDRITE_FEATURE_NAMES,
            progress=True,
        )
        in_dim = train_graphs[0].x.shape[1]
        cv_results = cross_validate(
            train_graphs, cfg, device, n_folds=5, in_dim=in_dim,
        )

        import numpy as np  # noqa: PLC0415
        median_best_epoch = int(np.median([r.best_epoch for r in cv_results]))
        final_epochs = max(median_best_epoch + 1, 30)
        model, scaler, test_metrics = fit_final(
            train_graphs, test_graphs, cfg, device,
            in_dim=in_dim, n_epochs=final_epochs,
        )

        gnn_out = output_dir / MODEL_FILES["gnn"]
        save_checkpoint(
            gnn_out, model, scaler, cfg,
            DENDRITE_FEATURE_NAMES, cv_results, test_metrics,
            final_epochs=final_epochs,
        )
        print(f"  saved {gnn_out}")

        cv_macro = float(
            np.mean([r.val_branch_macro_f1 for r in cv_results])
        )
        gnn_metrics = {
            "cv_macro_f1_mean": cv_macro,
            "test_metrics": test_metrics,
            "final_epochs": final_epochs,
        }

    print("\nTraining complete.")
    print(
        f"To use these models, set `SWCSTUDIO_MODEL_DIR={output_dir}` "
        f"or pass `--model-dir {output_dir}` on the CLI."
    )

    return TrainingResult(
        output_dir=str(output_dir),
        stage1_path=str(stage1_out),
        stage2_path=str(stage2_out),
        gnn_path=str(gnn_out) if gnn_out is not None else None,
        stage1_metrics=stage1_metrics or {},
        stage2_metrics=stage2_metrics or {},
        gnn_metrics=gnn_metrics,
    )


__all__ = ["train_user_models", "TrainingResult"]
