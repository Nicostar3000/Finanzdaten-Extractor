"""Kompatibilitaetsmodul fuer Portfolio-Analysefunktionen.

Die Implementierung liegt in `src/analysis/portfolio.py`.
"""

from .analysis.portfolio import (  # noqa: F401
    attach_source_file,
    build_broker_info_data,
    build_extracted_data,
    build_line_chart_data,
    build_pie_bucket_data,
    build_position_chart_data,
    calculate_file_validation_sums,
    combine_positions,
    filter_transactions,
    get_broker_filtered_transactions,
    get_bucket_positions,
    group_transactions_by_file,
    is_fee_transaction,
    is_purchase_transaction,
    summarize_transactions,
)

__all__ = [
    "get_broker_filtered_transactions",
    "filter_transactions",
    "summarize_transactions",
    "group_transactions_by_file",
    "combine_positions",
    "calculate_file_validation_sums",
    "build_position_chart_data",
    "build_pie_bucket_data",
    "get_bucket_positions",
    "build_line_chart_data",
    "build_broker_info_data",
    "build_extracted_data",
    "attach_source_file",
    "is_purchase_transaction",
    "is_fee_transaction",
]
