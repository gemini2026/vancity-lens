"""
Prepared statement management and safe parameterized query building for VanCity Lens.

This module provides:
- QueryBuilder class for constructing parameterized SQL queries safely
- PreparedStatementCache for caching frequently-used prepared statements
- Helper functions for building common query patterns
- Protection against SQL injection through proper parameterization
"""

import logging
from datetime import date
from typing import List, Tuple, Optional, Dict, Any
from collections import OrderedDict

logger = logging.getLogger(__name__)


class QueryBuilder:
    """
    Safe parameterized SQL query builder using asyncpg $N placeholder style.

    Constructs WHERE clauses and parameter lists dynamically while maintaining
    proper asyncpg parameter placeholders.
    """

    def __init__(self):
        """Initialize a new QueryBuilder with empty conditions and parameters."""
        self.conditions: List[str] = []
        self.params: List[Any] = []

    def add_filter(self, column: str, operator: str, value: Any) -> "QueryBuilder":
        """
        Add a simple column filter condition.

        Args:
            column: Column name (table.column format recommended)
            operator: Comparison operator (=, !=, >, <, >=, <=, LIKE, IN, etc.)
            value: Parameter value to filter by

        Returns:
            Self for method chaining
        """
        param_num = len(self.params) + 1
        placeholder = f"${param_num}"

        if operator.upper() in ("IN", "NOT IN"):
            # For IN/NOT IN, convert list to comma-separated placeholders
            if isinstance(value, (list, tuple)):
                placeholders = [f"${i + param_num}" for i in range(len(value))]
                self.conditions.append(
                    f"{column} {operator} ({', '.join(placeholders)})"
                )
                self.params.extend(value)
            else:
                raise ValueError(
                    f"IN operator requires list/tuple value, got {type(value)}"
                )
        else:
            self.conditions.append(f"{column} {operator} {placeholder}")
            self.params.append(value)

        return self

    def add_date_range(
        self,
        column: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> "QueryBuilder":
        """
        Add date range filter conditions.

        Args:
            column: Column name for date comparison
            from_date: Start date (inclusive), or None to skip
            to_date: End date (inclusive), or None to skip

        Returns:
            Self for method chaining
        """
        if from_date:
            param_num = len(self.params) + 1
            self.conditions.append(f"{column} >= ${param_num}")
            self.params.append(from_date)

        if to_date:
            param_num = len(self.params) + 1
            self.conditions.append(f"{column} <= ${param_num}")
            self.params.append(to_date)

        return self

    def add_severity_filter(self, severity_min: str) -> "QueryBuilder":
        """
        Add severity minimum filter using CASE expression.

        Maps severity strings to numeric levels for comparison.

        Args:
            severity_min: Minimum severity level ("info", "low", "medium", "high", "critical")

        Returns:
            Self for method chaining
        """
        severity_levels = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

        severity_val = severity_levels.get(severity_min.lower(), 0)
        severity_col = (
            "CASE isig.severity "
            "WHEN 'critical' THEN 4 "
            "WHEN 'high' THEN 3 "
            "WHEN 'medium' THEN 2 "
            "WHEN 'low' THEN 1 "
            "WHEN 'info' THEN 0 "
            "ELSE 0 END"
        )
        self.conditions.append(f"{severity_col} >= {severity_val}")

        return self

    def add_pagination(self, limit: int, offset: int) -> "QueryBuilder":
        """
        Add LIMIT and OFFSET parameters.

        Args:
            limit: Number of rows to return
            offset: Number of rows to skip

        Returns:
            Self for method chaining
        """
        self.params.append(limit)
        self.params.append(offset)

        return self

    def build(self) -> Tuple[str, List[Any]]:
        """
        Build the WHERE clause and return query string and parameters.

        Returns:
            Tuple of (where_clause_string, params_list)
            where_clause_string will be "1=1" if no conditions added
        """
        if not self.conditions:
            return "1=1", self.params

        where_clause = " AND ".join(self.conditions)
        return where_clause, self.params

    def get_limit_offset_placeholders(self) -> Tuple[str, str]:
        """
        Get the parameter placeholders for LIMIT and OFFSET.

        Must be called after add_pagination().

        Returns:
            Tuple of (limit_placeholder, offset_placeholder)
        """
        # Pagination params are added last
        total_params = len(self.params)
        if total_params < 2:
            raise ValueError(
                "add_pagination() must be called before getting placeholders"
            )

        limit_placeholder = f"${total_params - 1}"
        offset_placeholder = f"${total_params}"

        return limit_placeholder, offset_placeholder


class PreparedStatementCache:
    """
    LRU cache for prepared statements with maximum 50 cached statements.

    Reduces overhead of repeated query patterns by reusing prepared statements.
    """

    def __init__(self, max_statements: int = 50):
        """
        Initialize the cache.

        Args:
            max_statements: Maximum number of prepared statements to cache
        """
        self.max_statements = max_statements
        self.cache: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a prepared statement from cache.

        Updates LRU order by moving accessed item to end.

        Args:
            key: Cache key (usually the query string)

        Returns:
            Cached prepared statement or None if not found
        """
        if key in self.cache:
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            logger.debug(f"Prepared statement cache hit: {key[:50]}...")
            return self.cache[key]
        return None

    def put(self, key: str, prepared_stmt: Any) -> None:
        """
        Store a prepared statement in cache.

        Evicts oldest item if cache is full.

        Args:
            key: Cache key (usually the query string)
            prepared_stmt: The asyncpg prepared statement object
        """
        if key in self.cache:
            # Move to end if already exists
            self.cache.move_to_end(key)
        else:
            self.cache[key] = prepared_stmt
            # Evict oldest if over limit
            if len(self.cache) > self.max_statements:
                oldest_key, _ = self.cache.popitem(last=False)
                logger.debug(
                    f"Evicted prepared statement from cache: {oldest_key[:50]}..."
                )

    def clear(self) -> None:
        """Clear all cached prepared statements."""
        self.cache.clear()

    def stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache_size and max_statements
        """
        return {"cache_size": len(self.cache), "max_statements": self.max_statements}


def build_signal_feed_query(
    filters: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Any], str, str]:
    """
    Build a parameterized query for the signal feed endpoint.

    Args:
        filters: Dictionary with optional keys:
            - neighborhood: str
            - signal_type: str
            - severity_min: str
            - date_from: date
            - date_to: date
            - limit: int
            - offset: int

    Returns:
        Tuple of (feed_query_string, params_list, limit_placeholder, offset_placeholder)
    """
    if filters is None:
        filters = {}

    builder = QueryBuilder()

    # Add filters in a deterministic order
    if "neighborhood" in filters and filters["neighborhood"]:
        builder.add_filter("isig.neighborhood", "=", filters["neighborhood"])

    if "signal_type" in filters and filters["signal_type"]:
        builder.add_filter("isig.signal_type", "=", filters["signal_type"])

    if "decision" in filters and filters["decision"]:
        builder.add_filter("isig.decision", "=", filters["decision"])

    if "severity_min" in filters and filters["severity_min"]:
        builder.add_severity_filter(filters["severity_min"])

    if "date_from" in filters or "date_to" in filters:
        builder.add_date_range(
            "isig.event_date", filters.get("date_from"), filters.get("date_to")
        )

    # Add pagination
    limit = filters.get("limit", 20)
    offset = filters.get("offset", 0)
    builder.add_pagination(limit, offset)

    where_clause, params = builder.build()
    limit_placeholder, offset_placeholder = builder.get_limit_offset_placeholders()

    feed_query = f"""
        SELECT
            isig.id,
            isig.document_id,
            isig.signal_type,
            isig.summary,
            isig.headline,
            isig.addresses,
            isig.neighborhood,
            isig.decision,
            isig.vote_for,
            isig.vote_against,
            isig.sentiment,
            isig.severity,
            isig.confidence,
            isig.event_date,
            d.title AS source_title,
            d.source_url,
            d.source_type,
            d.published_date AS source_date
        FROM intelligence_signals isig
        JOIN documents d ON isig.document_id = d.id
        WHERE {where_clause}
        ORDER BY isig.event_date DESC, isig.id DESC
        LIMIT {limit_placeholder} OFFSET {offset_placeholder}
    """

    return feed_query, params, limit_placeholder, offset_placeholder


def build_signal_count_query(
    filters: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Any]]:
    """
    Build a parameterized query for counting signals with filters.

    Args:
        filters: Dictionary with optional keys (same as build_signal_feed_query):
            - neighborhood: str
            - signal_type: str
            - severity_min: str
            - date_from: date
            - date_to: date

    Returns:
        Tuple of (count_query_string, params_list)
    """
    if filters is None:
        filters = {}

    builder = QueryBuilder()

    # Add filters in a deterministic order (without pagination)
    if "neighborhood" in filters and filters["neighborhood"]:
        builder.add_filter("isig.neighborhood", "=", filters["neighborhood"])

    if "signal_type" in filters and filters["signal_type"]:
        builder.add_filter("isig.signal_type", "=", filters["signal_type"])

    if "decision" in filters and filters["decision"]:
        builder.add_filter("isig.decision", "=", filters["decision"])

    if "severity_min" in filters and filters["severity_min"]:
        builder.add_severity_filter(filters["severity_min"])

    if "date_from" in filters or "date_to" in filters:
        builder.add_date_range(
            "isig.event_date", filters.get("date_from"), filters.get("date_to")
        )

    where_clause, params = builder.build()

    count_query = f"""
        SELECT COUNT(*) as total
        FROM intelligence_signals isig
        WHERE {where_clause}
    """

    return count_query, params
