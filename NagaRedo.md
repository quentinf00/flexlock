I'm thinking of rethinking the naga architecture:


the highlevel endpoints would be:

```python
def clicfg():
    """
    add the argparse configuration and the default config fetching for default usage

    further more, I would like to be able to define the argv as args and kwargs and have them be parsed by the argparse for inspiration:


def get_parser():
    """Defines and returns the ArgumentParser object."""
    parser = argparse.ArgumentParser(description="A script to process data with a flexible calling interface.")
    
    # Positional Argument
    parser.add_argument("input_file", help="Path to the input file.")
    
    # Optional Arguments
    parser.add_argument("-o", "--output-file", default="output.txt",
                        help="Path to the output file (default: output.txt).")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose output.")
    parser.add_argument("--retries", type=int, default=3,
                        help="Number of retries for a task.")
                        
    return parser

def core_logic(args):
    '''
    The main logic of the script. It works with the parsed args object.
    This function doesn't care where the arguments came from (CLI or programmatic).
    '''
    print("--- Core Logic Execution ---")
    print(f"Input file: {args.input_file}")
    print(f"Output file: {args.output_file}")
    print(f"Retries: {args.retries}")
    if args.verbose:
        print("Verbose mode is ON.")
    print("--------------------------\n")

def main(*args, **kwargs):
    '''
    A wrapper function that can be called programmatically with *args and **kwargs
    or from the CLI.
    '''
    parser = get_parser()
    
    # Check if we are running from the CLI or programmatically
    if not args and not kwargs and len(sys.argv) > 1:
        # Standard CLI execution: parse sys.argv
        # The [1:] slice omits the script name itself
        parsed_args = parser.parse_args()
    else:
        # Programmatic execution: build argv list from *args and **kwargs
        argv = []
        
        # Add positional arguments from *args
        argv.extend([str(arg) for arg in args])
        
        # Add optional arguments from **kwargs
        for key, value in kwargs.items():
            # Convert python-style kwargs (e.g., output_file) to cli-style args (e.g., --output-file)
            arg_name = f"--{key.replace('_', '-')}"
            
            # Handle boolean flags (like --verbose)
            if isinstance(value, bool):
                if value:
                    argv.append(arg_name)
            # Handle other values
            else:
                argv.append(arg_name)
                argv.append(str(value))
                
        print(f"Programmatically constructed argv: {argv}")
        parsed_args = parser.parse_args(argv)
        
    # Run the core logic with the parsed arguments
    core_logic(parsed_args)

if __name__ == "__main__":
    # This block is only executed when the script is run directly from the command line
    print("Running from Command Line Interface...")
    main()

    # --- Example of programmatic calls ---
    print("\nRunning Programmatically (Example 1)...")
    main('my_input.txt', output_file='results.csv', verbose=True)
    
    print("Running Programmatically (Example 2)...")
    main('data/log.txt', retries=5)
    """
```
```python
def runlock(
    config, repos, data, prevs, runlock_path=lambda cfg: (cfg["save_dir"])/'run.lock', merge=False
):
    """
        Write run.lock file with keys
        config: stage configs
        repos: commits for each repo
        data: hash for each data path
        prevs: run.locks of dependent runs 

        the path can be explicitely specified (string or callable taking cfg as input else it looks for a save_dir key in the config and writes a run.lock in it
        
        merge specify if the run.lock data should be merged with exisiting file in case it already exists
```



```python
@context_manager
def mlflow_lock(path, runlock_file='run.lock'):
    """
    yields an mlflow run
    The path serves as logical run id, and manages tag to have deprecate previous run with the same logical run id, If the runlock file exists, it logs it 
    """
```


other utils:

unsafe_debug


NB: the resolvers can probably just call runlock(..., merge=True)
