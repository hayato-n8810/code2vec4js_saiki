import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
import sys


dataset_name = 'js_dataset'
max_contexts = '200'
word_vocab_size = '1301136'
path_vocab_size = '911417'
target_vocab_size = '261245'
num_threads = '64'


target_histogram_file = f'data/{dataset_name}/{dataset_name}.histo.tgt.c2v'
origin_histogram_file = f'data/{dataset_name}/{dataset_name}.histo.ori.c2v'
path_histogram_file = f'data/{dataset_name}/{dataset_name}.histo.path.c2v'


def work(page_id):
    test_dir = f'/data/js/{page_id}'
    test_data_file = f'/data/c2v/{page_id}.test.raw.txt'

    if os.path.isfile(f'/data/c2v/{page_id}.test.c2v') is True:
        return

    print(f'Extracting paths from test set... {test_dir}')
    with open(test_data_file, 'w') as fp:
        subprocess.run(['python3', 'JSExtractor/extract.py', '--dir', test_dir,
                        '--max_path_length', '8', '--max_path_width', '2'], stdout=fp)
        print('Finished extracting paths from test set')
    subprocess.run(['python3', 'preprocess_test.py', '--test_data', test_data_file, '--max_contexts', max_contexts, '--word_vocab_size', word_vocab_size, '--path_vocab_size',
                    path_vocab_size, '--target_vocab_size', target_vocab_size, '--word_histogram', origin_histogram_file, '--path_histogram', path_histogram_file, '--target_histogram', target_histogram_file, '--output_name', f'/data/c2v/{page_id}'])
    
    os.remove(test_data_file)



args = sys.argv
page_list = os.listdir('/data/js/')

with ProcessPoolExecutor() as executor:
    executor.map(work, page_list)
