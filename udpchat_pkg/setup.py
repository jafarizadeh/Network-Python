from setuptools import setup, find_packages

setup(
    name="udpchat",
    version="1.0.0",
    description="UDP chat client/server with private room support",
    author="Your Name",
    packages=find_packages(),  
    install_requires=[
        "colorama",
    ],
    entry_points={
        "console_scripts": [
            "udpchat-server = udpchat.server:main",
            "udpchat-client = udpchat.client:main",
        ],
    },
    python_requires=">=3.7",
)
