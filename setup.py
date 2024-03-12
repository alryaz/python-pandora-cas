import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pandora-cas",
    author="Alexander Ryazanov",
    author_email="alryaz@alryaz.com",
    description="Pandora Car Alarm System clientside API implementation",
    keywords="pandora, car, alarm, system, alarmtrade",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/alryaz/python-pandora-cas",
    project_urls={
        "Documentation": "https://github.com/alryaz/python-pandora-cas",
        "Bug Reports": "https://github.com/alryaz/python-pandora-cas/issues",
        "Source Code": "https://github.com/alryaz/python-pandora-cas",
        # 'Funding': '',
        # 'Say Thanks!': '',
    },
    package_dir={"": "src"},
    packages=setuptools.find_packages(where="src"),
    classifiers=[
        # see https://pypi.org/classifiers/
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3 :: Only",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
    # install_requires=['Pillow'],
    extras_require={
        "dev": ["check-manifest"],
        # 'test': ['coverage'],
    },
    # entry_points={
    #     'console_scripts': [
    #         'run=pandora_cas:main',
    #     ],
    # },
)
