from setuptools import setup, find_packages

setup(
    name="globus-ec2ssh",
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        'boto3==1.4.7',
    ],
    entry_points={
        'console_scripts': [
            'ec2ssh = ec2ssh.ec2ssh:main',
            '_ec2ssh_complete_py = ec2ssh.complete_instances:main'
        ],
    },
)
