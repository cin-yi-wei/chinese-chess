// 中國象棋引擎的 stdin/stdout JSON REPL（非 Qt 版本）
// 人類執黑棋盤下方紅方（RED），AI 執黑方（BLACK）並使用 MCTS（Search::searchMain）。
// 每行讀入一個 JSON 物件，每行輸出一個 JSON 物件，輸出後立即 flush。
#include <iostream>
#include <string>
#include <vector>
#include <cstdio>
#include "position.h"
#include "search.h"

static const std::string START_FEN =
    "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR";

static Position g;

// 重置為開局盤面（Position 有 const 成員，無法整體賦值，改為手動清空歷史堆疊）
static void resetNew() {
    g.mvList.clear();
    g.pcList.clear();
    g.keyList.clear();
    g.chkList.clear();
    g.distance = 0;
    g.fromFen(START_FEN); // 內部 clearBoard + setIrrev
    g.chkList.push_back(g.checked()); // 對齊參考版 main 的初始化
}

// 針對目前走棋方，回傳所有「真正合法」的走法（generateMoves 中 makeMove 成功者）
static std::vector<unsigned short> computeLegal(Position &p) {
    std::vector<unsigned short> out;
    std::vector<unsigned short> ms = p.generateMoves();
    for (size_t i = 0; i < ms.size(); i++) {
        if (p.makeMove(ms[i])) {
            p.undoMakeMove();
            out.push_back(ms[i]);
        }
    }
    return out;
}

// ---- 極簡 JSON 取值輔助 ----
static std::string jsonGetStr(const std::string &s, const std::string &key) {
    std::string k = "\"" + key + "\"";
    size_t p = s.find(k);
    if (p == std::string::npos) return "";
    p = s.find(':', p + k.size());
    if (p == std::string::npos) return "";
    p = s.find('"', p);
    if (p == std::string::npos) return "";
    size_t q = s.find('"', p + 1);
    if (q == std::string::npos) return "";
    return s.substr(p + 1, q - p - 1);
}

static bool jsonGetPair(const std::string &s, const std::string &key, int &a, int &b) {
    std::string k = "\"" + key + "\"";
    size_t p = s.find(k);
    if (p == std::string::npos) return false;
    p = s.find('[', p);
    if (p == std::string::npos) return false;
    size_t q = s.find(']', p);
    if (q == std::string::npos) return false;
    std::string inner = s.substr(p + 1, q - p - 1);
    return sscanf(inner.c_str(), " %d , %d", &a, &b) == 2;
}

// 將走法轉為 [fx,fy,tx,ty]
static std::string moveToCoords(unsigned short mv) {
    int fx = Position::sqToFileX(g.SRC(mv));
    int fy = Position::sqToRankY(g.SRC(mv));
    int tx = Position::sqToFileX(g.DST(mv));
    int ty = Position::sqToRankY(g.DST(mv));
    char buf[64];
    snprintf(buf, sizeof(buf), "[%d,%d,%d,%d]", fx, fy, tx, ty);
    return std::string(buf);
}

// 輸出局面狀態 JSON
static void emitState(const std::vector<unsigned short> &legal, bool hasAi, unsigned short aiMv) {
    bool redToMove = !g.sdPlayer;      // sdPlayer==false(0) 為紅方
    bool inCheck = g.checked();
    bool over = legal.empty();

    std::string out = "{";
    out += "\"fen\":\"" + g.toFen() + "\",";
    out += std::string("\"redToMove\":") + (redToMove ? "true" : "false") + ",";
    out += std::string("\"inCheck\":") + (inCheck ? "true" : "false") + ",";

    out += "\"legal\":[";
    for (size_t i = 0; i < legal.size(); i++) {
        if (i) out += ",";
        out += moveToCoords(legal[i]);
    }
    out += "],";

    if (hasAi) {
        out += "\"aiMove\":" + moveToCoords(aiMv) + ",";
    }

    // 走棋方無合法步 → 對方勝
    if (over) {
        std::string winner = g.sdPlayer ? "red" : "black"; // 黑方無步紅勝，反之黑勝
        out += "\"gameOver\":\"" + winner + "\"";
    } else {
        out += "\"gameOver\":null";
    }
    out += "}";

    std::cout << out << "\n";
    std::cout.flush();
}

int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.find_first_not_of(" \t\r\n") == std::string::npos) continue;

        std::string cmd = jsonGetStr(line, "cmd");

        if (cmd == "new") {
            resetNew();
            emitState(computeLegal(g), false, 0);
        } else if (cmd == "move") {
            int fx, fy, tx, ty;
            if (!jsonGetPair(line, "from", fx, fy) || !jsonGetPair(line, "to", tx, ty)) {
                std::cout << "{\"illegal\":true}\n";
                std::cout.flush();
                continue;
            }
            unsigned short mv = g.MOVE(Position::coordToSq(fx, fy), Position::coordToSq(tx, ty));

            // 是否為偽合法走法（在 generateMoves 中）
            std::vector<unsigned short> pseudo = g.generateMoves();
            bool member = false;
            for (size_t i = 0; i < pseudo.size(); i++) {
                if (pseudo[i] == mv) { member = true; break; }
            }
            if (!member || !g.makeMove(mv)) { // makeMove 失敗會自行還原
                std::cout << "{\"illegal\":true}\n";
                std::cout.flush();
                continue;
            }

            // 人類走完後，換 AI（黑方）。先看黑方是否已無步（人類獲勝）。
            std::vector<unsigned short> legalAfter = computeLegal(g);
            if (legalAfter.empty()) {
                emitState(legalAfter, false, 0); // gameOver
                continue;
            }

            // AI 用 MCTS 產生走法並落子
            Search search(&g);
            unsigned short aiMv = search.searchMain();
            g.makeMove(aiMv); // 即使失敗（受保留 bug 影響）仍回報該步

            std::vector<unsigned short> legalFinal = computeLegal(g);
            emitState(legalFinal, true, aiMv);
        } else {
            std::cout << "{\"illegal\":true}\n";
            std::cout.flush();
        }
    }
    return 0;
}
