"""訓練超參數。PoC 用小值先跑通；要真的強再把網路/模擬數/對局數放大。"""

# 網路規模
CHANNELS = 128
BLOCKS = 10

# 自我對弈
GAMES_PER_ITER = 30      # 每輪自我對弈局數
SIMS = 400               # 每步 PUCT 模擬數（自我對弈：深一點的搜尋=更強的訓練目標）
SELFPLAY_BATCH = 96      # 批次葉評估大小（速度/搜尋品質權衡；非記憶體瓶頸）
TEMP_MOVES = 30          # 前幾步用溫度取樣增加多樣性，之後取最高訪問
MAX_MOVES = 200          # 單局上限（達到判和）
C_PUCT = 1.5
DIRICHLET_ALPHA = 0.3    # 根節點 Dirichlet 探索雜訊參數（AlphaZero 標準；僅自我對弈）
DIRICHLET_FRAC = 0.25    # 雜訊混合比例；0=關閉

# 平行自我對弈
NUM_WORKERS = 8          # 降載防當機

# 課程訓練：對 Rust alpha-beta 老師（0=關閉，純 AZ vs AZ 自我對弈；>0=老師搜尋層數）
OPPONENT_DEPTH = 0       # 0=純 AZ 自我對弈(zero 對 zero)；>0=對 alpha-beta 老師課程

# 監督式模仿暖啟動（imitate.py）：模仿此深度的 alpha-beta 著法
IMITATE_DEPTH = 2        # 交叉訓練師父階梯起點（貼近網路現況，變強再升）
IMITATE_EPS = 0.2        # 產資料時以此機率走隨機著法（增加局面多樣性，off-trajectory 覆蓋）
DAGGER = False           # True=用「網路自己的手」走子、老師標註（修分佈偏移）；False=純模仿老師軌跡
IMITATE_RAND_OPEN = 8    # 每局開頭先走 0~此值步隨機著法 → 訓練涵蓋多樣開局（對齊隨機開局評測，修通用化）

# 執行控制
MAX_MINUTES = 15         # 交叉訓練:每段跑 ~15 分鐘就停（換另一種訓練）

# 訓練
ITERATIONS = 1000000     # 大迴圈上限（實際由 MAX_MINUTES 控制每段時長）
EPOCHS = 1               # 交叉訓練:兩段都用 1
BATCH_SIZE = 256
LR = 1e-3
WEIGHT_DECAY = 1e-4
REPLAY_WINDOW = 2        # 交叉訓練:小窗

CKPT_DIR = "checkpoints"
