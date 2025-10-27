import random
from argparse import ArgumentParser
import common
import pickle
import os
import sys

'''
This script preprocesses the data from MethodPaths. It truncates methods with too many contexts,
and pads methods with less paths with spaces.

Optimization: Supports loading histograms from cache file for faster parallel execution.
'''


def save_dictionaries(dataset_name, word_to_count, path_to_count, target_to_count,
                      num_training_examples):
    save_dict_file_path = '{}.dict.c2v'.format(dataset_name)
    with open(save_dict_file_path, 'wb') as file:
        pickle.dump(word_to_count, file)
        pickle.dump(path_to_count, file)
        pickle.dump(target_to_count, file)
        pickle.dump(num_training_examples, file)
        print('Dictionaries saved to: {}'.format(save_dict_file_path))

 
def process_file(file_path, data_file_role, dataset_name, word_to_count, path_to_count, max_contexts):
    import tempfile
    
    sum_total = 0
    sum_sampled = 0
    total = 0
    empty = 0
    max_unfiltered = 0
    output_path = '{}.{}.c2v'.format(dataset_name, data_file_role)
    
    # Use atomic write: write to temp file first, then rename
    output_dir = os.path.dirname(output_path) or '.'
    os.makedirs(output_dir, exist_ok=True)
    
    temp_fd, temp_path = tempfile.mkstemp(suffix='.c2v', dir=output_dir, text=True)
    
    try:
        with os.fdopen(temp_fd, 'w') as outfile:
            with open(file_path, 'r') as file:
                for line in file:
                    parts = line.rstrip('\n').split(' ')
                    target_name = parts[0]
                    contexts = parts[1:]

                    if len(contexts) > max_unfiltered:
                        max_unfiltered = len(contexts)
                    sum_total += len(contexts)

                    if len(contexts) > max_contexts:
                        context_parts = [c.split(',') for c in contexts]
                        full_found_contexts = [c for i, c in enumerate(contexts)
                                               if context_full_found(context_parts[i], word_to_count, path_to_count)]
                        partial_found_contexts = [c for i, c in enumerate(contexts)
                                                  if context_partial_found(context_parts[i], word_to_count, path_to_count)
                                                  and not context_full_found(context_parts[i], word_to_count,
                                                                             path_to_count)]
                        if len(full_found_contexts) > max_contexts:
                            contexts = random.sample(full_found_contexts, max_contexts)
                        elif len(full_found_contexts) <= max_contexts \
                                and len(full_found_contexts) + len(partial_found_contexts) > max_contexts:
                            contexts = full_found_contexts + \
                                       random.sample(partial_found_contexts, max_contexts - len(full_found_contexts))
                        else:
                            contexts = full_found_contexts + partial_found_contexts

                    if len(contexts) == 0:
                        empty += 1
                        continue

                    sum_sampled += len(contexts)

                    csv_padding = " " * (max_contexts - len(contexts))
                    outfile.write(target_name + ' ' + " ".join(contexts) + csv_padding + '\n')
                    total += 1
        
        # Atomic rename: move temp file to final location
        os.replace(temp_path, output_path)
        
    except Exception as e:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise

    print('File: ' + file_path)
    print('Average total contexts: ' + str(float(sum_total) / total))
    print('Average final (after sampling) contexts: ' + str(float(sum_sampled) / total))
    print('Total examples: ' + str(total))
    print('Empty examples: ' + str(empty))
    print('Max number of contexts per word: ' + str(max_unfiltered))
    return total


def context_full_found(context_parts, word_to_count, path_to_count):
    return context_parts[0] in word_to_count \
           and context_parts[1] in path_to_count and context_parts[2] in word_to_count


def context_partial_found(context_parts, word_to_count, path_to_count):
    return context_parts[0] in word_to_count \
           or context_parts[1] in path_to_count or context_parts[2] in word_to_count


if __name__ == '__main__':
    parser = ArgumentParser()
    # parser.add_argument("-trd", "--train_data", dest="train_data_path",
    #                     help="path to training data file", required=True)
    parser.add_argument("-ted", "--test_data", dest="test_data_path",
                        help="path to test data file", required=True)
    # parser.add_argument("-vd", "--val_data", dest="val_data_path",
    #                     help="path to validation data file", required=True)
    parser.add_argument("-mc", "--max_contexts", dest="max_contexts", default=200,
                        help="number of max contexts to keep", required=False)
    parser.add_argument("-wvs", "--word_vocab_size", dest="word_vocab_size", default=1301136,
                        help="Max number of origin word in to keep in the vocabulary", required=False)
    parser.add_argument("-pvs", "--path_vocab_size", dest="path_vocab_size", default=911417,
                        help="Max number of paths to keep in the vocabulary", required=False)
    parser.add_argument("-tvs", "--target_vocab_size", dest="target_vocab_size", default=261245,
                        help="Max number of target words to keep in the vocabulary", required=False)
    parser.add_argument("-wh", "--word_histogram", dest="word_histogram",
                        help="word histogram file", metavar="FILE", required=True)
    parser.add_argument("-ph", "--path_histogram", dest="path_histogram",
                        help="path_histogram file", metavar="FILE", required=True)
    parser.add_argument("-th", "--target_histogram", dest="target_histogram",
                        help="target histogram file", metavar="FILE", required=True)
    parser.add_argument("-o", "--output_name", dest="output_name",
                        help="output name - the base name for the created dataset", metavar="FILE", required=True,
                        default='data')
    args = parser.parse_args()

    try:
        # train_data_path = args.train_data_path
        test_data_path = args.test_data_path
        # val_data_path = args.val_data_path
        word_histogram_path = args.word_histogram
        path_histogram_path = args.path_histogram

        # Validate input file exists
        if not os.path.exists(test_data_path):
            print(f'[ERROR] Test data file not found: {test_data_path}', file=sys.stderr)
            sys.exit(1)

        # Try to load from cache first for faster parallel execution
        cache_file = None
        if word_histogram_path:
            # Derive cache file path from histogram path
            histo_dir = os.path.dirname(word_histogram_path)
            cache_file = os.path.join(histo_dir, 'histogram_cache.pkl')
        
        if cache_file and os.path.exists(cache_file):
            # Fast path: Load from cache
            print(f'Loading histograms from cache: {cache_file}', file=sys.stderr)
            try:
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    word_to_count = cache_data['word_to_count']
                    path_to_count = cache_data['path_to_count']
                    target_to_count = cache_data['target_to_count']
                    print(f'Loaded from cache: {len(word_to_count)} words, {len(path_to_count)} paths, {len(target_to_count)} targets', file=sys.stderr)
            except Exception as e:
                print(f'Warning: Failed to load cache ({e}), falling back to raw histograms', file=sys.stderr)
                cache_file = None
        
        if not cache_file or not os.path.exists(cache_file):
            # Slow path: Load from raw histogram files
            print('Loading histograms from raw files (consider running preload_histograms.py)', file=sys.stderr)
            
            # Validate histogram files exist
            for histo_file in [word_histogram_path, path_histogram_path, args.target_histogram]:
                if not os.path.exists(histo_file):
                    print(f'[ERROR] Histogram file not found: {histo_file}', file=sys.stderr)
                    sys.exit(1)
            
            word_histogram_data = common.common.load_vocab_from_histogram(word_histogram_path, start_from=1,
                                                                          max_size=int(args.word_vocab_size),
                                                                          return_counts=True)
            _, _, _, word_to_count = word_histogram_data
            _, _, _, path_to_count = common.common.load_vocab_from_histogram(path_histogram_path, start_from=1,
                                                                             max_size=int(args.path_vocab_size),
                                                                             return_counts=True)
            _, _, _, target_to_count = common.common.load_vocab_from_histogram(args.target_histogram, start_from=1,
                                                                               max_size=int(args.target_vocab_size),
                                                                               return_counts=True)

        # num_training_examples = 0
        # for data_file_path, data_role in zip([test_data_path, val_data_path, train_data_path], ['test', 'val', 'train']):
        for data_file_path, data_role in zip([test_data_path], ['test']):
            num_examples = process_file(file_path=data_file_path, data_file_role=data_role, dataset_name=args.output_name,
                                        word_to_count=word_to_count, path_to_count=path_to_count,
                                        max_contexts=int(args.max_contexts))
            
            if num_examples == 0:
                print(f'[WARN] No examples were processed from {data_file_path}', file=sys.stderr)
        #     if data_role == 'train':
        #         num_training_examples = num_examples

        # save_dictionaries(dataset_name=args.output_name, word_to_count=word_to_count,
        #                   path_to_count=path_to_count, target_to_count=target_to_count,
        #                   num_training_examples=num_training_examples)

    except KeyboardInterrupt:
        print('\n[INFO] Interrupted by user', file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f'\n[ERROR] Preprocessing failed: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
