"""訓練超參數。PoC 用小值先跑通；要真的強再把網路/模擬數/對局數放大。"""

# 網路規模
CHANNELS = 128
BLOCKS = 10

# 自我對弈
GAMES_PER_ITER = 50      # 每輪自我對弈局數（正式可設數百~數千）
SIMS = 200               # 每步 PUCT 模擬數（正式可設 400~800+）
TEMP_MOVES = 30          # 前幾步用溫度取樣增加多樣性，之後取最高訪問
MAX_MOVES = 200          # 單局上限（達到判和）
C_PUCT = 1.5

# 訓練
ITERATIONS = 1000        # 自我對弈↔訓練 的大迴圈輪數
EPOCHS = 2               # 每輪對收集到的資料訓練幾遍
BATCH_SIZE = 256
LR = 1e-3
WEIGHT_DECAY = 1e-4
REPLAY_WINDOW = 20       # 保留最近幾輪的資料一起訓練

CKPT_DIR = "checkpoints"
