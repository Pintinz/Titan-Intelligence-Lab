# TitanIQ — Probability Calibration

Status: **Milestone 9, extended by Milestone 9.1**. "Only calibrated probabilities may be
returned" (Milestone 9.1 spec) — this doc covers the 3 `CalibratorPort` implementations and the
reporting layer that lets a human verify that policy is actually being honored, not just
declared.

## 1. `CalibratorPort`

```python
class CalibratorPort(Protocol):
    async def calibrate(self, model_id: ModelId, raw_probability: float) -> float: ...
    async def fit(self, model_id: ModelId, samples: list[tuple[float, bool]]) -> None: ...
```

Kept separate from `PredictorPort`: a predictor scores a market; a calibrator maps that
predictor's raw output onto a well-calibrated probability using that model's own observed outcome
history. Before `fit()` has run for a model, every implementation below returns the identity
mapping — an honestly-scoped "no calibration data yet" default (ADR-008), not a faked result.

## 2. The 3 methods

| Method | Class | Shape | Parameters learned |
|---|---|---|---|
| Platt Scaling | `PlattScalingCalibrator` (Milestone 9) | `sigmoid(A·logit(raw) + B)` | 2 (`A`, `B`), pure-Python batch gradient descent |
| Isotonic Regression | `IsotonicRegressionCalibrator` | Non-parametric monotonic step function (`sklearn.isotonic.IsotonicRegression`) | Arbitrary — fits better when miscalibration isn't a simple sigmoid distortion |
| Temperature Scaling | `TemperatureScalingCalibrator` | `sigmoid(logit(raw) / T)` | 1 (`T`), pure-Python batch gradient descent |

Temperature Scaling is symmetric around 0.5 by construction (`logit(0.5) == 0`, so `0/T == 0` for
any `T`) and can only sharpen/soften confidence, never reorder predictions — the lightest-weight
of the three, useful when a 1-parameter correction is enough. Platt Scaling adds a bias term (`B`)
Temperature Scaling doesn't have. Isotonic Regression is the most expressive but the least
parametric (no closed form to reason about, just a fitted step function).

Gradient derivation for Temperature Scaling (documented once, since it's less standard than
Platt's): for one sample `(x=logit(raw), y=outcome)` with `p=sigmoid(x/T)`,
`dL/dT = x·(y-p)/T²` — the standard binary-cross-entropy `dL/dp` and the sigmoid derivative
`dp/dT`'s `p·(1-p)` factors cancel.

## 3. Reliability Curves & Calibration Reports

`CalibrationReportBuilder.build(method, samples, now)` computes:

- **Reliability Curve** (`build_reliability_curve`) — buckets `(probability, outcome)` samples
  into `n_bins` (default 10), each bucket's `predicted_mean` vs. `actual_rate` — a diagonal curve
  means well-calibrated.
- **Expected Calibration Error** — the sample-count-weighted mean absolute gap between predicted
  and actual rate across bins. Near 0 means well-calibrated.
- **Brier Score** — mean squared error between probability and the binary outcome.

A `CalibrationReport` (method, sample count, ECE, Brier score, reliability curve, generated_at)
is a report a human can verify the "only calibrated probabilities" policy against — a diagonal
curve and near-zero ECE both indicate the policy holds, rather than trusting it's declared true.

## 4. Calibration Drift

`ModelMonitoringService.calibration_drift(current_samples, baseline_samples, now)`
([model_registry.md](model_registry.md) §6) builds two `CalibrationReport`s and compares their
ECE — a model well-calibrated at deployment but drifted since needs recalibration, not just
retraining.

## 5. Persistence

Migration `0023_ml_platform_schema`: `calibration_reports` (one row per `build()` call) — the
persisted record a `ModelDefinition.calibration_report_ref` points to.

## 6. APIs

`POST /api/v1/admin/ml/calibration/reports` (`apps.api.routers.ml_platform_router`,
`Role.ADMINISTRATOR`-gated) — builds a report on demand from supplied samples.

## 7. Testing & Coverage

`isotonic_regression_calibrator.py` 100%, `temperature_scaling_calibrator.py` 100%,
`calibration_reporting_service.py` 100% — measured with `pytest-cov`
(`test_isotonic_regression_calibrator.py`, `test_temperature_scaling_calibrator.py`,
`test_calibration_reporting_service.py`, plus `test_platt_scaling_calibrator.py` from Milestone 9).
