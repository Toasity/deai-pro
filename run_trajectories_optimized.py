

session = python_session()
code_optimizer = Optimizer()
for script in pipelines:
    code = load_script_from_py(script)
    
    code_optimizer.optimize(code)
    
    
    results = session.run_script(code)
    
    
    write(results)
    compare_(results)