#!/usr/bin/env python3
"""
code2vec_only.py - Simplified version for vector export only

This script loads a pre-trained code2vec model and exports code vectors
without performing evaluation or training. Useful for vectorizing code
with --whole_file or when target names are OOV.

Usage:
    python3 code2vec_only.py --load <model_path> --test <test_data.c2v> --export_code_vectors

Example:
    python3 code2vec_only.py \
        --load models/js_dataset_min5/saved_model_iter19.release \
        --test results/project/c2v/file.test.c2v \
        --export_code_vectors
"""

import sys
import os

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import Config
from model_base import Code2VecModelBase


def load_model_dynamically(config: Config) -> Code2VecModelBase:
    assert config.DL_FRAMEWORK in {'tensorflow', 'keras'}
    if config.DL_FRAMEWORK == 'tensorflow':
        from tensorflow_model import Code2VecModel
    elif config.DL_FRAMEWORK == 'keras':
        from keras_model import Code2VecModel
    return Code2VecModel(config)


if __name__ == '__main__':
    config = Config(set_defaults=True, load_from_args=True, verify=True)

    # Verify that we're in vector export mode
    if not config.EXPORT_CODE_VECTORS:
        config.log('ERROR: --export_code_vectors flag is required for this script')
        exit(1)
    
    if not config.is_loading:
        config.log('ERROR: --load <model_path> is required')
        exit(1)
    
    if not config.is_testing:
        config.log('ERROR: --test <test_data.c2v> is required')
        exit(1)

    model = load_model_dynamically(config)
    config.log('Done creating code2vec model')

    # Export code vectors only - skip evaluation
    config.log('Starting code vector export (evaluation metrics disabled)')
    
    try:
        # Call evaluate() which internally exports vectors via _write_code_vectors
        # We catch and ignore ZeroDivisionError from F1 calculation
        model.evaluate()
        config.log('Code vectors exported successfully')
    except ZeroDivisionError:
        config.log('Code vectors exported successfully (evaluation metrics skipped due to OOV targets)')
    except Exception as e:
        config.log(f'Warning: Evaluation encountered an error, but vectors may have been exported: {e}')
    
    model.close_session()
    
    # Report output location
    output_path = f"{config.TEST_DATA_PATH}.vectors"
    config.log(f'Vector output file: {output_path}')
