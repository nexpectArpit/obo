import json
from pathlib import Path

# Paths
TRACKS_DIR = Path(__file__).resolve().parent.parent / "tracks"

# Define the advanced, specific topics to append to each track
EXPANSION_TOPICS = {
    "cpp": [
        # DP Optimization & Classical Patterns
        {
            "name": "Dynamic Programming: 0/1 and Unbounded Knapsack Problem Variants",
            "prompt": "explain 0/1 knapsack and unbounded knapsack, and solve subset sum, partition equal subset sum, and change coins problem patterns",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Dynamic Programming: Longest Common Subsequence and Edit Distance",
            "prompt": "explain LCS transition, solve edit distance, shortest common supersequence, and delete operation for two strings",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Dynamic Programming: Longest Increasing Subsequence and Coordinate Compression",
            "prompt": "explain O(N log N) LIS using binary search, solve Russian doll envelopes, and apply coordinate compression to LIS variants",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Dynamic Programming: Interval DP and Matrix Chain Multiplication",
            "prompt": "explain interval DP state definition dp[i][j], solve matrix chain multiplication, burst balloons, and minimum cost to merge stones",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Dynamic Programming: Bitmask DP and Hamiltonian Path Problems",
            "prompt": "explain state compression using bitmasks, solve traveling salesman problem, and find Hamiltonian paths in graphs",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Dynamic Programming: DP on Trees and Tree Diameter Optimization",
            "prompt": "explain tree DP using post-order traversal, solve tree diameter, maximum path sum, and binary tree coloring game",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Dynamic Programming: Digit DP and Numeric Constraints",
            "prompt": "explain digit DP technique, count numbers with unique digits in a range [L, R] satisfying digit constraints",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Dynamic Programming: Probability and Expectation DP",
            "prompt": "explain probability DP state transition, solve soup servings, and calculate expected steps to reach a goal in a grid",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Dynamic Programming: Convex Hull Trick and DP Optimization",
            "prompt": "explain Convex Hull Trick (CHT) for O(N) DP optimization, slope trick, and Knuth's optimization for interval DP",
            "covered": False, "level_at_cover": 0
        },
        # Algorithmic Optimization & Advanced Structures
        {
            "name": "Algorithms: Subarray Optimization Patterns",
            "prompt": "explain Kadane's algorithm, sliding window maximum using monotonic deque, and finding subarray sum equals K using prefix hashmap",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Algorithms: Segment Tree with Lazy Propagation",
            "prompt": "implement segment tree with lazy propagation for range updates and range queries in O(log N), and solve range addition query",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Algorithms: Fenwick Tree (Binary Indexed Tree) for Multi-Dimensional Range Sums",
            "prompt": "implement 1D and 2D Fenwick Trees, perform point updates and prefix sum queries, and solve range query point update",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Algorithms: Sparse Table for Constant Time Range Minimum Queries",
            "prompt": "implement sparse table, explain precomputation in O(N log N), and perform constant time O(1) range minimum queries",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Algorithms: Tarjan's and Kosaraju's Strongly Connected Components",
            "prompt": "explain Kosaraju's double DFS algorithm and Tarjan's single-pass DFS algorithm for finding strongly connected components in directed graphs",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Algorithms: Hierholzer's Algorithm for Eulerian Paths",
            "prompt": "explain Eulerian path conditions for directed and undirected graphs, and implement Hierholzer's algorithm to reconstruct paths",
            "covered": False, "level_at_cover": 0
        }
    ],
    "arch": [
        # Cache & Performance Optimizations
        {
            "name": "Cache Performance: Cache Blocking and Matrix Multiplication Optimization",
            "prompt": "explain cache blocking (tiling) to optimize matrix multiplication, spatial vs temporal locality, and sizing blocks to fit L1/L2 caches",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Cache Performance: Stride Access Patterns and Spatial Locality",
            "prompt": "explain stride-1 vs non-unit stride memory access patterns, how cache lines prefetch sequential blocks, and loop interchange to fix stride",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Cache Performance: Cache Pollution and Conflict Misses",
            "prompt": "explain conflict misses in direct-mapped and set-associative caches, cache way alignment, and avoiding cache pollution with non-temporal prefetch",
            "covered": False, "level_at_cover": 0
        },
        # Execution & Hazards
        {
            "name": "Instruction Execution: Pipeline Hazards and Branch Target Buffers",
            "prompt": "explain structural, data, and control pipeline hazards, and how branch target buffers (BTB) minimize branch penalties",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Instruction Execution: Out-of-Order Execution and Register Renaming",
            "prompt": "explain Tomasulo's algorithm for out-of-order execution, reservation stations, and register renaming to resolve WAR/WAW hazards",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Instruction Execution: Speculative Execution and Cache Side Channels",
            "prompt": "explain speculative execution, branch prediction direction, and how CPU speculation transient states create cache timing side channels",
            "covered": False, "level_at_cover": 0
        },
        # Hardware Memory Interface
        {
            "name": "Memory Interface: HBM3e Memory Channels and Cache Hierarchy Coherence",
            "prompt": "explain HBM3e high-bandwidth memory channel layout, cache coherence protocols (MESI/MOESI), and directory-based coherence for multi-socket systems",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Memory Interface: NUMA Architecture and Memory Access Latency",
            "prompt": "explain Non-Uniform Memory Access (NUMA) node affinity, local vs remote memory latency, and page migration strategies in OS",
            "covered": False, "level_at_cover": 0
        },
        # Network Optimizations
        {
            "name": "Network Performance: TCP Window Scaling and Buffer Sizing",
            "prompt": "explain TCP sliding window flow control, window scaling option for high-delay networks, and tuning socket send/receive buffer sizes",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Network Performance: TCP Congestion Control Algorithms (BBR vs Cubic)",
            "prompt": "compare loss-based congestion control (Cubic) with delay/bandwidth-based control (BBR), explaining throughput and queue buildup trade-offs",
            "covered": False, "level_at_cover": 0
        }
    ],
    "os": [
        # Concurrency & Locking Internals
        {
            "name": "Concurrency: Spinlock vs Mutex Overhead and Sleep Queues",
            "prompt": "compare spinlocks with mutexes, explaining busy-waiting vs context switching overhead, thread suspension, and kernel sleep queues",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Concurrency: Lock-Free Structures and Compare-And-Swap (CAS) Operations",
            "prompt": "explain lock-free programming principles, lock-free stack/queue implementation using atomic CAS operations, and the ABA problem",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Concurrency: Read-Copy-Update (RCU) Kernel Synchronization",
            "prompt": "explain Read-Copy-Update (RCU) lockless read synchronization, deferred deletion, grace periods, and quiescent states in kernel threads",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Concurrency: Priority Inversion and Priority Inheritance Protocols",
            "prompt": "explain priority inversion in real-time preemptive schedulers, and how priority inheritance and priority ceiling protocols resolve it",
            "covered": False, "level_at_cover": 0
        },
        # Scheduler Internals
        {
            "name": "OS Scheduling: CFS Scheduler Virtual Runtime Calculations",
            "prompt": "explain Linux Completely Fair Scheduler (CFS) red-black tree layout, priority-to-weight mapping, and virtual runtime calculations",
            "covered": False, "level_at_cover": 0
        },
        # Virtual Memory & Address Translation
        {
            "name": "Virtual Memory: Hierarchical Page Table Walks and Translation Lookaside Buffer",
            "prompt": "explain multi-level page tables, virtual-to-physical address translation steps, and TLB hit/miss penalty mitigation",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Virtual Memory: TLB Shootdowns in Symmetric Multiprocessing",
            "prompt": "explain TLB shootdown process, inter-processor interrupts (IPI) for page table modification, and overhead of multiprocessor address consistency",
            "covered": False, "level_at_cover": 0
        },
        # File System Internals
        {
            "name": "File Systems: ext4 Journaling Modes and Write-Ahead Log Optimizations",
            "prompt": "compare ext4 journaling modes (journal, ordered, writeback), write-ahead log barriers, and metadata recovery consistency",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "File Systems: ZFS Copy-on-Write Page Mapping and Merkle Tree Integrity",
            "prompt": "explain ZFS Copy-on-Write (CoW) page allocation, transaction groups, and Merkle tree block checksum verification for data integrity",
            "covered": False, "level_at_cover": 0
        }
    ],
    "ds": [
        # Statistical Testing
        {
            "name": "Statistical Inference: A/B Testing Statistical Power and Sample Size Sizing",
            "prompt": "explain statistical power (1 - Beta), significance level (Alpha), effect size, and calculating required sample size for A/B split tests",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Statistical Inference: ANOVA F-Statistic Calculation and Multiple Comparisons",
            "prompt": "explain Analysis of Variance (ANOVA), sum of squares partition, F-statistic derivation, and Bonferroni correction for multiple hypothesis tests",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Statistical Inference: Chi-Square Test of Independence and Goodness-of-Fit",
            "prompt": "explain Chi-Square distribution degrees of freedom, calculating observed vs expected contingency tables, and testing category dependencies",
            "covered": False, "level_at_cover": 0
        },
        # Regression & Dimensionality Diagnostics
        {
            "name": "Regression Diagnostics: Multicollinearity and Variance Inflation Factors",
            "prompt": "explain multicollinearity in linear models, calculate Variance Inflation Factors (VIF), and diagnose high-variance coefficients",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Regression Diagnostics: Heteroscedasticity and Residual Homoscedasticity Tests",
            "prompt": "explain heteroscedasticity, evaluate residual plots, and run Breusch-Pagan / White tests to verify constant variance assumptions",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Dimensionality Reduction: Principal Component Analysis Singular Value Decomposition",
            "prompt": "explain PCA projection maximization, covariance matrix diagonalization, and how singular value decomposition (SVD) solves PCA without covariance",
            "covered": False, "level_at_cover": 0
        },
        # Clustering Metrics
        {
            "name": "Clustering Validation: Silhouette Coefficient and Davies-Bouldin Index",
            "prompt": "explain silhouette width calculation, Davies-Bouldin clustering index, and selecting optimal K clusters using validation indices",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Clustering Algorithms: DBSCAN Epsilon Neighborhood and Core Points",
            "prompt": "explain density-based spatial clustering parameters (Epsilon, MinPts), Core, Border, and Noise points classifications, and handling arbitrary shapes",
            "covered": False, "level_at_cover": 0
        }
    ],
    "dl": [
        # Calculus & Backprop Traces
        {
            "name": "Deep Backpropagation: Softmax with Cross-Entropy Gradient Derivation",
            "prompt": "derive analytical partial derivatives of cross-entropy loss with respect to pre-activation softmax inputs, separating target vs non-target classes",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Deep Backpropagation: Layer Normalization Backward Pass Math",
            "prompt": "derive backward pass gradients for Layer Normalization, explaining mean/variance derivative paths and input feature dependencies",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Deep Backpropagation: Gated RNN Vanishing Gradient Pathways",
            "prompt": "analyze backward pass gradient routes in LSTMs and GRUs, showing how additive cell state transitions prevent exponential decay",
            "covered": False, "level_at_cover": 0
        },
        # Attention Mechanisms
        {
            "name": "Attention Mechanisms: Multi-Head Self-Attention Projection Sizes",
            "prompt": "explain Scaled Dot-Product Attention, Multi-Head projection matrix shapes (W_q, W_k, W_v, W_o), and relative memory footprints",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Attention Mechanisms: Rotary Positional Embedding (RoPE) Mathematical Formulations",
            "prompt": "explain Rotary Positional Embedding (RoPE), 2D vector rotation matrices, and relative position tracking in Multi-Head attention",
            "covered": False, "level_at_cover": 0
        },
        # Optimizers & Normalization
        {
            "name": "Optimization Tricks: Layer-wise Adaptive Rate Scaling (LARS)",
            "prompt": "explain Layer-wise Adaptive Rate Scaling (LARS), compute layer-wise local learning rates based on weight and gradient norms for large batch training",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Optimization Tricks: Weight Decay vs L2 Regularization in AdamW",
            "prompt": "explain why decoupling weight decay from gradient updates (AdamW) differs from standard L2 regularization in adaptive optimizers",
            "covered": False, "level_at_cover": 0
        }
    ],
    "maths": [
        # Optimization Math
        {
            "name": "Numerical Optimization: Quasi-Newton Methods (BFGS Update Step)",
            "prompt": "explain Quasi-Newton BFGS optimization, the secant equation, and formulating rank-2 updates to approximate the inverse Hessian matrix",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Numerical Optimization: Memory-Reduced L-BFGS Two-Loop Recursion",
            "prompt": "explain Limited-memory BFGS (L-BFGS), state saving using vector history, and the two-loop recursion algorithm to compute search directions",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Numerical Optimization: Newton-Raphson Step Size and Convergence Rates",
            "prompt": "explain multi-dimensional Newton's optimization step delta x = - H^(-1) * g, and quadratic convergence guarantees",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Constrained Optimization: Karush-Kuhn-Tucker (KKT) Conditions",
            "prompt": "explain Karush-Kuhn-Tucker (KKT) stationarity, primal feasibility, dual feasibility, and complementary slackness conditions for inequality constraints",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Constrained Optimization: Lagrange Multipliers and Support Vector Boundaries",
            "prompt": "explain method of Lagrange multipliers, formulating dual optimization problems, and finding optimal hyperplanes in support vector machines",
            "covered": False, "level_at_cover": 0
        },
        # Matrix Decomposition
        {
            "name": "Linear Algebra: Singular Value Decomposition Low-Rank Matrix Approximation",
            "prompt": "explain Singular Value Decomposition (SVD) matrix factorization A = U * Sigma * V^T, and Eckart-Young-Mirsky low-rank matrix approximation",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Linear Algebra: Eigenvalue and Eigenvector Diagonalization",
            "prompt": "explain eigenvector diagonalization A = P * D * P^(-1), characteristic polynomial calculations, and geometric vs algebraic multiplicity",
            "covered": False, "level_at_cover": 0
        },
        # Probability & Modeling
        {
            "name": "Probability: Bayes Theorem and Gaussian Mixture Models",
            "prompt": "explain Bayes theorem, prior/likelihood/posterior probability formulations, and parameter fitting in Gaussian Mixture Models (GMM)",
            "covered": False, "level_at_cover": 0
        },
        {
            "name": "Probability: Markov Chains Transition Probabilities and Steady State",
            "prompt": "explain discrete-time Markov chains, transition probability matrices, stationary distribution vectors, and absorbing states",
            "covered": False, "level_at_cover": 0
        }
    ]
}

# Load, expand, and write back track JSON files
for track_key, new_topics in EXPANSION_TOPICS.items():
    # Find matching filename in tracks/
    for filepath in TRACKS_DIR.iterdir():
        if filepath.suffix == ".json" and filepath.name.startswith(("1_", "2_", "3_", "4_", "5_", "6_")):
            with open(filepath, "r") as f:
                track_data = json.load(f)
            
            if track_data.get("track_name") == track_key:
                # Deduplicate and append topics based on unique name
                existing_names = {t.get("name") for t in track_data.get("topics", [])}
                appended = 0
                for nt in new_topics:
                    if nt["name"] not in existing_names:
                        track_data["topics"].append(nt)
                        appended += 1
                
                with open(filepath, "w") as f:
                    json.dump(track_data, f, indent=2)
                
                print(f"[SUCCESS] Expanded track '{track_key}' with {appended} new topics. Total topics: {len(track_data['topics'])}")
                break
