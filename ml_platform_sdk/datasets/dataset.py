import logging
import os
import shutil
from typing import Optional
from urllib.parse import urlparse
import requests

from ml_platform_sdk import initializer
from ml_platform_sdk.config import credential as auth_credential, constants
from ml_platform_sdk.tos import tos
from ml_platform_sdk.openapi import client


def dataset_copy_file(metadata, source_dir, destination_dir):
    file_path = metadata['Data']['FilePath']
    file_dir, file_name = os.path.split(file_path)
    target_dir = os.path.join(destination_dir,
                              os.path.relpath(file_dir, start=source_dir))

    # create output file directory
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError:
        logging.warning('Cannot create directory: %s', target_dir)

    target_file = os.path.join(target_dir, file_name)
    shutil.copy(file_path, target_file)
    metadata['Data']['FilePath'] = target_file


class _Dataset:
    """
    datasets object
    """

    def __init__(self,
                 dataset_id: Optional[str] = None,
                 local_path: Optional[str] = None,
                 tos_source: Optional[str] = None,
                 credential: Optional[auth_credential.Credential] = None):
        self.dataset_id = dataset_id
        self.local_path = local_path
        self.tos_source = tos_source
        self.created = False
        self.data_count = 0
        self.detail = None
        self.credential = credential or initializer.global_config.get_credential(
        )
        self.tos_client = tos.TOSClient(credential)
        self.api_client = client.APIClient(credential)

    def _get_detail(self):
        if self.dataset_id is None:
            return
        try:
            self.detail = self.api_client.get_dataset(self.dataset_id)['Result']
        except Exception as e:
            logging.error('get datasets detail failed, error: %s', e)
            raise Exception('invalid datasets') from e

    def _get_storage_path(self) -> str:
        if self.detail is None:
            return ""
        return self.detail['StoragePath']

    def _manifest_path(self):
        return os.path.join(self.local_path,
                            constants.DATASET_LOCAL_METADATA_FILENAME)

    def _download_file(self, url, target_dir, chunk_size=8192):
        parse_result = urlparse(url)
        file_path = os.path.join(target_dir, parse_result.path[1:])
        dir_path, _ = os.path.split(file_path)

        # create file directory
        try:
            os.makedirs(dir_path, exist_ok=True)
        except OSError:
            logging.warning('Cannot create download directory: %s', dir_path)

        # download file base on url schemes
        if parse_result.scheme == 'https' or parse_result.scheme == 'http':
            # write response chunks in file
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(file_path, 'wb+') as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        f.write(chunk)
        elif parse_result.scheme == 'tos':
            bucket = parse_result.netloc.split('.')[0]
            key = parse_result.path[1:]
            self.tos_client.download_file(file_path, bucket, key)
        else:
            logging.warning('Cannot handle url scheme: %s', url)
            raise requests.exceptions.InvalidURL

        return file_path
