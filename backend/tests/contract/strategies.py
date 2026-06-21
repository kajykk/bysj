"""Hypothesis strategies for generating boundary test data.

Provides custom strategies for contract testing with edge cases and boundary values.
"""

from __future__ import annotations

from hypothesis import strategies as st


# Structured prediction boundary values
STRUCTURED_FEATURES = {
    "sleep_hours": st.one_of(
        st.just(0.0),  # Minimum
        st.just(24.0),  # Maximum
        st.floats(min_value=0.0, max_value=24.0),  # Normal range
        st.floats(min_value=-100.0, max_value=-0.1),  # Negative (invalid)
        st.floats(min_value=24.1, max_value=100.0),  # Over max (invalid)
    ),
    "exercise_minutes": st.one_of(
        st.just(0.0),
        st.just(300.0),
        st.floats(min_value=0.0, max_value=300.0),
        st.floats(min_value=-100.0, max_value=-0.1),
    ),
    "heart_rate_avg": st.one_of(
        st.just(40.0),
        st.just(200.0),
        st.floats(min_value=40.0, max_value=200.0),
        st.floats(min_value=0.0, max_value=39.9),
    ),
    "steps": st.one_of(
        st.just(0),
        st.integers(min_value=0, max_value=50000),
        st.integers(min_value=-1000, max_value=-1),
    ),
}


def structured_input_strategy():
    """Generate structured prediction inputs with boundary values."""
    return st.fixed_dictionaries({
        "sleep_hours": STRUCTURED_FEATURES["sleep_hours"],
        "exercise_minutes": STRUCTURED_FEATURES["exercise_minutes"],
    }, optional={
        "heart_rate_avg": STRUCTURED_FEATURES["heart_rate_avg"],
        "steps": STRUCTURED_FEATURES["steps"],
    })


# Text prediction boundary values
def text_input_strategy():
    """Generate text inputs with various boundary conditions."""
    return st.fixed_dictionaries({
        "text": st.one_of(
            st.just(""),  # Empty
            st.just("a"),  # Single char
            st.text(min_size=1, max_size=10),  # Short
            st.text(min_size=100, max_size=500),  # Medium
            st.text(min_size=1000, max_size=2000),  # Long
            st.sampled_from([
                "I feel happy today",
                "I feel very sad and depressed",
                "I am extremely anxious about everything",
                "Life is good, no complaints",
                "",  # Empty
                "   ",  # Whitespace only
                "a" * 10000,  # Very long
            ]),
        ),
    })


# Physiological prediction boundary values
def physiological_input_strategy():
    """Generate physiological inputs with boundary values."""
    return st.fixed_dictionaries({
        "sleep_hours": st.one_of(
            st.just(0.0),
            st.just(24.0),
            st.floats(min_value=0.0, max_value=24.0),
            st.just(-1.0),
            st.just(25.0),
        ),
        "exercise_minutes": st.one_of(
            st.just(0.0),
            st.just(300.0),
            st.floats(min_value=0.0, max_value=300.0),
        ),
    }, optional={
        "heart_rate_avg": st.floats(min_value=30.0, max_value=250.0),
        "steps": st.integers(min_value=0, max_value=100000),
    })


# Fusion prediction boundary values
def fusion_input_strategy():
    """Generate fusion inputs with various combinations."""
    return st.one_of(
        # Both text and structured
        st.fixed_dictionaries({
            "text": st.text(min_size=1, max_size=100),
            "structured": st.fixed_dictionaries({
                "sleep_hours": st.floats(min_value=0.0, max_value=24.0),
            }),
        }),
        # Text only
        st.fixed_dictionaries({
            "text": st.text(min_size=1, max_size=100),
        }),
        # Structured only
        st.fixed_dictionaries({
            "structured": st.fixed_dictionaries({
                "sleep_hours": st.floats(min_value=0.0, max_value=24.0),
            }),
        }),
        # Empty
        st.just({}),
    )


# Auth boundary values
def login_input_strategy():
    """Generate login inputs with boundary values."""
    return st.fixed_dictionaries({
        "username": st.one_of(
            st.just(""),
            st.just("a"),
            st.emails(),
            st.text(min_size=1, max_size=50),
        ),
        "password": st.one_of(
            st.just(""),
            st.just("123"),
            st.text(min_size=8, max_size=50),
        ),
    })


def register_input_strategy():
    """Generate registration inputs with boundary values."""
    return st.fixed_dictionaries({
        "email": st.one_of(
            st.just(""),
            st.just("invalid"),
            st.emails(),
        ),
        "password": st.one_of(
            st.just(""),
            st.just("short"),
            st.text(min_size=8, max_size=50),
        ),
    }, optional={
        "name": st.one_of(
            st.just(""),
            st.text(min_size=1, max_size=100),
        ),
    })


# Monitoring boundary values
def time_range_strategy():
    """Generate time range parameters."""
    return st.fixed_dictionaries({
        "start_time": st.one_of(
            st.just("2024-01-01T00:00:00Z"),
            st.just("invalid"),
            st.just(""),
        ),
        "end_time": st.one_of(
            st.just("2024-12-31T23:59:59Z"),
            st.just("invalid"),
            st.just(""),
        ),
    })


# Export request boundary values
def export_request_strategy():
    """Generate export request inputs."""
    return st.fixed_dictionaries({
        "report_type": st.one_of(
            st.just("prediction_summary"),
            st.just("user_activity"),
            st.just("invalid_type"),
            st.just(""),
        ),
    }, optional={
        "start_date": st.just("2024-01-01"),
        "end_date": st.just("2024-12-31"),
    })
