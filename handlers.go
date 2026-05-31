package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
)

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func membersHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		members, err := GetMembers()
		if err != nil {
			writeError(w, 500, err.Error())
			return
		}
		if members == nil {
			members = []Member{}
		}
		writeJSON(w, 200, members)

	case http.MethodPost:
		var req struct {
			Nickname string `json:"nickname"`
			Level    string `json:"level"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, 400, "invalid request body")
			return
		}
		req.Nickname = strings.TrimSpace(req.Nickname)
		req.Level = strings.ToUpper(strings.TrimSpace(req.Level))
		if req.Nickname == "" {
			writeError(w, 400, "nickname is required")
			return
		}
		if req.Level != "C" && req.Level != "B" && req.Level != "A" && req.Level != "S" {
			writeError(w, 400, "level must be C, B, A, or S")
			return
		}
		m, err := AddMember(req.Nickname, req.Level)
		if err != nil {
			if strings.Contains(err.Error(), "UNIQUE") {
				writeError(w, 409, "nickname already exists")
				return
			}
			writeError(w, 500, err.Error())
			return
		}
		writeJSON(w, 201, m)

	default:
		writeError(w, 405, "method not allowed")
	}
}

func matchesHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		matches, err := GetMatches()
		if err != nil {
			writeError(w, 500, err.Error())
			return
		}
		if matches == nil {
			matches = []Match{}
		}
		writeJSON(w, 200, matches)

	case http.MethodPost:
		var req struct {
			CourtType  string `json:"court_type"`
			MatchDate  string `json:"match_date"`
			Scores     string `json:"scores"`
			WinnerTeam int    `json:"winner_team"`
			Team1IDs   []int  `json:"team1_ids"`
			Team2IDs   []int  `json:"team2_ids"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, 400, "invalid request body")
			return
		}

		req.CourtType = strings.ToLower(strings.TrimSpace(req.CourtType))
		if req.CourtType != "singles" && req.CourtType != "doubles" {
			writeError(w, 400, "court_type must be singles or doubles")
			return
		}
		if req.MatchDate == "" {
			writeError(w, 400, "match_date is required")
			return
		}
		if req.Scores == "" {
			writeError(w, 400, "scores is required")
			return
		}
		if req.WinnerTeam != 1 && req.WinnerTeam != 2 {
			writeError(w, 400, "winner_team must be 1 or 2")
			return
		}

		expectedPerTeam := 1
		if req.CourtType == "doubles" {
			expectedPerTeam = 2
		}
		if len(req.Team1IDs) != expectedPerTeam || len(req.Team2IDs) != expectedPerTeam {
			writeError(w, 400, fmt.Sprintf("%s requires %d player(s) per team", req.CourtType, expectedPerTeam))
			return
		}

		allIDs := append(req.Team1IDs, req.Team2IDs...)
		seen := make(map[int]bool)
		for _, id := range allIDs {
			if seen[id] {
				writeError(w, 400, "a player cannot appear on both teams")
				return
			}
			seen[id] = true
			m, err := GetMemberByID(id)
			if err != nil {
				writeError(w, 500, err.Error())
				return
			}
			if m == nil {
				writeError(w, 400, fmt.Sprintf("member id %d not found", id))
				return
			}
		}

		m, err := AddMatch(req.CourtType, req.MatchDate, req.Scores, req.WinnerTeam, req.Team1IDs, req.Team2IDs)
		if err != nil {
			writeError(w, 500, err.Error())
			return
		}
		writeJSON(w, 201, m)

	default:
		writeError(w, 405, "method not allowed")
	}
}

func leaderboardHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, 405, "method not allowed")
		return
	}
	entries, err := GetLeaderboard()
	if err != nil {
		writeError(w, 500, err.Error())
		return
	}
	if entries == nil {
		entries = []LeaderboardEntry{}
	}
	writeJSON(w, 200, entries)
}

func memberHistoryHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, 405, "method not allowed")
		return
	}
	path := strings.TrimPrefix(r.URL.Path, "/api/members/")
	idStr := strings.TrimSuffix(path, "/history")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		writeError(w, 400, "invalid member id")
		return
	}
	history, err := GetMemberHistory(id)
	if err != nil {
		writeError(w, 500, err.Error())
		return
	}
	if history == nil {
		writeError(w, 404, "member not found")
		return
	}
	writeJSON(w, 200, history)
}

func activeMemberHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, 405, "method not allowed")
		return
	}
	active, err := GetMostActiveThisMonth()
	if err != nil {
		writeError(w, 500, err.Error())
		return
	}
	if active == nil {
		writeJSON(w, 200, nil)
		return
	}
	writeJSON(w, 200, active)
}
