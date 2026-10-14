# TODO

Accepted implementation scope only. Promote an item from [IDEAS.md](IDEAS.md)
after its protocol, constraints, compatibility effects, and validation plan have
been agreed. Record completed investigations and durable decisions in
[DONE.md](DONE.md).

## Active

No implementation task has yet been formally accepted through this planning
folder.

## Decisions required before the next training campaign

Two choices are one-way doors and should be written down before looking at new
results:

1. Which periods, months, or events are reserved as the untouched test set
   ([I1](IDEAS.md#i1--leakage-resistant-data-split)). Once their performance is
   inspected, they have effectively become development data.
2. Which spatial and temporal gates, source versions, deduplication rules, and
   quality filters define the frozen independent validation set
   ([I2](IDEAS.md#i2--frozen-independent-measurement-validation-set)). Changing
   collocation rules during an ablation campaign changes the metric itself.

## Recommended promotion order

1. Promote I1 as a leakage audit and split-protocol task. Do not tune model
   architecture or high-sea losses before this baseline is trustworthy.
2. Promote I2 as a frozen altimeter/buoy validation-product task, including
   stable identifiers and a versioned manifest.
3. Run I3, the offline gradient-target validity diagnostic. It requires no new
   training and can proceed while I1 and I2 data products are prepared.
4. Add the small I4 anti-collapse metrics to the re-baseline run.
5. Promote I5 only after I1-I3 settle the split, scoring metric, and treatment
   of the gradient loss.
6. Audit calibration in I6 before choosing the production/export head in I7.
7. Promote I8 spectrum consolidation independently when the current alignment
   risk or Lustre metadata cost is confirmed on the active data path.
8. Build the I10/I11 result products before implementing the proposed SAR-ML
   explorers; the UI should consume stable products rather than repair joins.

## Promotion template

### T<number> — Title

- **Accepted:** YYYY-MM-DD
- **Origin:** `IDEAS.md` section

**Goal:**

**Accepted scope:**

**Non-goals:**

**Compatibility and invalidation:**

**Validation:**

**Completion criteria:**
