import json
from pathlib import Path

def adapt_track_target_skills(active_track_name, current_targets, learned_skills, achieved_skills, get_track_path_fn):
    """
    Data Analysis & Dynamic Steering:
    Compares all recorded and newly achieved skills for the active track,
    identifies the top highest-level skills, updates the track's target_skills in JSON,
    and inclines the next chat sessions directly in that direction to compound mastery to LV 100+.
    """
    if not active_track_name:
        return

    try:
        track_path = get_track_path_fn(active_track_name)
        if track_path and track_path.exists():
            with open(track_path, "r") as f:
                track_data = json.load(f)
            
            # Combine learned_skills and achieved_skills
            all_skills = dict(learned_skills or {})
            for sk, lv_val in (achieved_skills or {}).items():
                try:
                    lvl_num = int(str(lv_val).replace("LV", "").strip())
                    if lvl_num > all_skills.get(sk, 0):
                        all_skills[sk] = lvl_num
                except ValueError:
                    pass

            if not all_skills:
                return

            track_keywords = {
                "cpp": ["cpp", "c++", "algorithm", "algorithms", "data structure", "data structures", "tree", "graph", "dynamic programming", "dp", "stack", "queue", "pointer", "array", "string", "hash", "hashing", "sorting", "trie", "bitmask", "bitwise", "binary search", "segment tree", "fenwick tree", "bit", "sparse table", "union find", "disjoint set", "dsu", "shortest path", "dijkstra", "bellman ford", "floyd warshall", "mst", "kruskal", "prim", "topological sort", "backtracking", "greedy", "two pointers", "sliding window", "prefix sum", "suffix array", "kmp", "rabin karp", "z algorithm", "bipartite", "maximum flow", "min cut", "centroid decomposition", "heavy light decomposition", "computational geometry", "convex hull", "sweep line"],
                "arch": ["architecture", "memory", "cache", "pipeline", "networking", "network", "tcp", "ip", "socket", "cpu", "bus", "assembly", "instruction set", "isa", "risc", "cisc", "x86", "arm", "out-of-order", "superscalar", "branch prediction", "virtual memory", "mmu", "tlb", "dma", "i/o", "interrupt", "multiprocessor", "coherence", "consistency", "numa", "smp", "gpu architecture", "simd", "fpga", "asic", "verilog", "vhdl", "routing", "switching", "bgp", "ospf", "dns", "http", "udp", "mac address", "arp", "subnet", "vlans", "osi model", "data link", "physical layer"],
                "os": ["operating system", "operating systems", "os", "thread", "threads", "process", "processes", "syscall", "syscalls", "system call", "system calls", "mutex", "semaphore", "virtual memory", "paging", "file system", "concurrency", "kernel", "kernels", "module", "modules", "linux", "windows", "macos", "unix", "posix", "scheduler", "scheduling", "cfs", "deadlock", "spinlock", "context switch", "pcb", "tcb", "fork", "exec", "inter-process communication", "ipc", "pipe", "shared memory", "signal", "inode", "ext4", "ntfs", "fat32", "zfs", "device driver", "bootloader", "grub", "virtualization", "hypervisor", "namespace", "cgroup", "docker", "container"],
                "ds": ["data science", "machine learning", "statistics", "hypothesis", "regression", "probability", "pandas", "numpy", "eda", "clustering", "classification", "scikit-learn", "sklearn", "data preprocessing", "feature engineering", "imputation", "outlier detection", "pca", "dimensionality reduction", "k-means", "dbscan", "hierarchical clustering", "decision tree", "random forest", "xgboost", "lightgbm", "catboost", "svm", "support vector machine", "knn", "naive bayes", "logistic regression", "linear regression", "r-squared", "p-value", "anova", "t-test", "chi-square", "a/b testing", "time series", "arima", "forecasting", "cross-validation", "grid search"],
                "dl": ["deep learning", "neural network", "neural networks", "gradient descent", "sgd", "convolution", "convolutional", "cnn", "transformer", "attention", "loss", "backprop", "backpropagation", "activation", "perceptron", "mlp", "rnn", "lstm", "gru", "autoencoder", "gan", "diffusion model", "generative", "llm", "large language model", "bert", "gpt", "pytorch", "tensorflow", "keras", "tensor", "batch normalization", "dropout", "regularizer", "weight decay", "adam", "rmsprop", "learning rate", "epoch", "forward pass", "pooling", "softmax", "relu", "sigmoid", "cross entropy"],
                "maths": ["algebra", "linear algebra", "calculus", "matrix", "matrices", "vector", "vectors", "optimization", "probability", "eigen", "eigenvalue", "eigenvector", "derivative", "partial derivative", "gradient", "hessian", "jacobian", "integral", "differential equation", "convex", "convexity", "concave", "quasi-newton", "bfgs", "l-bfgs", "second-order", "numerical methods", "taylor series", "fourier transform", "laplace", "tensor calculus", "statistics theory", "distributions", "normal distribution", "gaussian", "poisson", "binomial", "bayes theorem", "bayesian", "markov chain", "stochastic", "monte carlo", "combinatorics"]
            }
            
            import re
            keywords = track_keywords.get(active_track_name.lower(), [])
            
            # Filter skills relevant to this track
            relevant_skills = []
            for skill_name, lvl in all_skills.items():
                sk_lower = skill_name.lower()
                is_relevant = False
                for kw in keywords:
                    pattern = r'\b' + re.escape(kw.lower()) + r'\b'
                    if re.search(pattern, sk_lower):
                        is_relevant = True
                        break
                if not is_relevant and active_track_name.lower() in sk_lower:
                    is_relevant = True
                if is_relevant:
                    relevant_skills.append((skill_name, lvl))
                    
            if not relevant_skills:
                # If no keyword matched, use all available skills
                relevant_skills = list(all_skills.items())

            # Sort by highest skill level descending — normalize all values to int first
            # to prevent TypeError when learned_skills contains mixed str/int values
            def _to_int_level(v):
                try:
                    return int(str(v).replace("LV", "").replace("lv", "").strip())
                except (ValueError, AttributeError):
                    return 0

            relevant_skills.sort(key=lambda x: _to_int_level(x[1]), reverse=True)
            
            # Pick the top 2 highest leveled skills to steer the chat
            top_targets = [sk for sk, _ in relevant_skills[:2]]
            
            if top_targets:
                print(f"\n>>> [DYNAMIC STEERING] Top Mastery Skills in Track '{active_track_name}': {relevant_skills[:3]} <<<")
                print(f">>> [DYNAMIC STEERING] Updating target focus to: {top_targets} to incline conversation towards highest growth! <<<\n")
                track_data["target_skills"] = top_targets
                with open(track_path, "w") as f:
                    json.dump(track_data, f, indent=2)
    except Exception as ex:
        print(f"[WARNING] Failed dynamic skill adaptation: {ex}")
