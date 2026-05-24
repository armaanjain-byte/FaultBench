"""FaultBench package setup."""

from setuptools import find_packages, setup

setup(
    name="faultbench",
    version="0.1.0",
    description="Stress-test coding agents under adversarial runtime conditions",
    author="FaultBench Contributors",
    python_requires=">=3.11",
    packages=find_packages(exclude=["tests", "tests.*"]),
    include_package_data=True,
    package_data={
        "faultbench": ["db/*.sql", "reporting/templates/*.j2"],
    },
    install_requires=[
        "docker>=6.1.0",
        "pyyaml>=6.0",
        "structlog>=23.0",
        "click>=8.1",
        "requests>=2.31.0",
        "httpx>=0.24.0",
        "jinja2>=3.1",
        "matplotlib>=3.7",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4",
            "pytest-cov>=4.1",
        ],
    },
    entry_points={
        "console_scripts": [
            "faultbench=faultbench.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Testing",
    ],
)
