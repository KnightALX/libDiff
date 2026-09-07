"""Library comparison."""

from libdiff.compare.diff import compare_libraries, export_json, export_csv
from libdiff.compare.timing_qa import (
    timing_qa,
    export_timing_qa_json,
    export_timing_qa_csv,
    format_timing_qa_summary,
    single_lib_timing_qa,
    delta_matrices,
    check_monotonicity,
    run_timing_qa_batch,
    export_timing_qa_batch_csv,
    export_timing_qa_html,
    format_timing_qa_batch_summary,
)
from libdiff.compare.ppa import (
    compare_ppa,
    export_ppa_json,
    export_ppa_csv,
    export_ppa_html,
    format_ppa_summary,
    typical_delay,
    cell_leakage_total,
)

from libdiff.compare.lut_index import (
    classify_lut,
    resolve_indices,
    sample_lut,
    resample_to_grid,
    cross_index_delta,
    slice_curve,
    probe_points,
)

__all__ = [
    "compare_libraries",
    "export_json",
    "export_csv",
    "timing_qa",
    "export_timing_qa_json",
    "export_timing_qa_csv",
    "format_timing_qa_summary",
    "single_lib_timing_qa",
    "delta_matrices",
    "check_monotonicity",
    "run_timing_qa_batch",
    "export_timing_qa_batch_csv",
    "export_timing_qa_html",
    "format_timing_qa_batch_summary",
    "compare_ppa",
    "export_ppa_json",
    "export_ppa_csv",
    "export_ppa_html",
    "format_ppa_summary",
    "typical_delay",
    "cell_leakage_total",

    "classify_lut",
    "resolve_indices",
    "sample_lut",
    "resample_to_grid",
    "cross_index_delta",
    "slice_curve",
    "probe_points",
]
