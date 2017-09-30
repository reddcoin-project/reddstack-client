#!/usr/bin/python

from setuptools import setup, find_packages

# to set __version__
exec(open('blockstore_client/version.py').read())

setup(
    name='blockstore-client',
    version=__version__,
    url='https://github.com/reddcoin-project/blockstore-client',
    license='GPLv3',
    author='Blockstack.org',
    author_email='support@blockstack.org',
    description='Python client library for Blockstore',
    keywords='blockchain bitcoin btc cryptocurrency name key value store data',
    packages=find_packages(),
    scripts=['bin/blockstore-cli', 'bin/blockstore'],
    download_url='https://github.com/reddcoin-project/blockstore-client/archive/master.zip',
    zip_safe=False,
    include_package_data=True,
    install_requires=[
        'boto==2.38.0',
        'basicrpc==0.0.2',
        'virtualchain==0.0.8',
        'protocoin==0.1'
    ],
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet',
        'Topic :: Security :: Cryptography',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
