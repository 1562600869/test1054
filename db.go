package main

import (
	"database/sql"
	"fmt"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

type Member struct {
	ID       int    `json:"id"`
	Nickname string `json:"nickname"`
	Level    string `json:"level"`
	JoinDate string `json:"join_date"`
}

type Match struct {
	ID         int      `json:"id"`
	CourtType  string   `json:"court_type"`
	MatchDate  string   `json:"match_date"`
	Scores     string   `json:"scores"`
	WinnerTeam int      `json:"winner_team"`
	Team1      []Member `json:"team1"`
	Team2      []Member `json:"team2"`
}

type LeaderboardEntry struct {
	ID       int    `json:"id"`
	Nickname string `json:"nickname"`
	Level    string `json:"level"`
	Points   int    `json:"points"`
	Wins     int    `json:"wins"`
	Losses   int    `json:"losses"`
}

type OpponentStats struct {
	ID       int    `json:"id"`
	Nickname string `json:"nickname"`
	Played   int    `json:"played"`
}

type MemberHistory struct {
	Member    Member         `json:"member"`
	Wins      int            `json:"wins"`
	Losses    int            `json:"losses"`
	Opponents []OpponentStats `json:"opponents"`
}

type ActiveMember struct {
	ID              int    `json:"id"`
	Nickname        string `json:"nickname"`
	Level           string `json:"level"`
	MatchesThisMonth int   `json:"matches_this_month"`
}

var db *sql.DB

func InitDB(dbPath string) error {
	var err error
	db, err = sql.Open("sqlite3", dbPath)
	if err != nil {
		return fmt.Errorf("open db: %w", err)
	}

	schema := `
	CREATE TABLE IF NOT EXISTS members (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		nickname TEXT NOT NULL UNIQUE,
		level TEXT NOT NULL CHECK(level IN ('C', 'B', 'A', 'S')),
		join_date TEXT NOT NULL
	);
	CREATE TABLE IF NOT EXISTS matches (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		court_type TEXT NOT NULL CHECK(court_type IN ('singles', 'doubles')),
		match_date TEXT NOT NULL,
		scores TEXT NOT NULL,
		winner_team INTEGER NOT NULL CHECK(winner_team IN (1, 2)),
		created_at TEXT DEFAULT (datetime('now'))
	);
	CREATE TABLE IF NOT EXISTS match_players (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		match_id INTEGER NOT NULL,
		member_id INTEGER NOT NULL,
		team INTEGER NOT NULL CHECK(team IN (1, 2)),
		FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
		FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
	);
	`

	_, err = db.Exec(schema)
	if err != nil {
		return fmt.Errorf("create tables: %w", err)
	}

	return nil
}

func AddMember(nickname, level string) (*Member, error) {
	if level != "C" && level != "B" && level != "A" && level != "S" {
		return nil, fmt.Errorf("invalid level: must be C, B, A, or S")
	}
	now := time.Now().Format("2006-01-02")
	result, err := db.Exec("INSERT INTO members (nickname, level, join_date) VALUES (?, ?, ?)", nickname, level, now)
	if err != nil {
		return nil, fmt.Errorf("insert member: %w", err)
	}
	id, _ := result.LastInsertId()
	return &Member{ID: int(id), Nickname: nickname, Level: level, JoinDate: now}, nil
}

func GetMembers() ([]Member, error) {
	rows, err := db.Query("SELECT id, nickname, level, join_date FROM members ORDER BY id")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var members []Member
	for rows.Next() {
		var m Member
		if err := rows.Scan(&m.ID, &m.Nickname, &m.Level, &m.JoinDate); err != nil {
			return nil, err
		}
		members = append(members, m)
	}
	return members, nil
}

func GetMemberByID(id int) (*Member, error) {
	var m Member
	err := db.QueryRow("SELECT id, nickname, level, join_date FROM members WHERE id = ?", id).Scan(&m.ID, &m.Nickname, &m.Level, &m.JoinDate)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &m, nil
}

func AddMatch(courtType, matchDate, scores string, winnerTeam int, team1IDs, team2IDs []int) (*Match, error) {
	if courtType != "singles" && courtType != "doubles" {
		return nil, fmt.Errorf("invalid court_type: must be singles or doubles")
	}

	expectedPerTeam := 1
	if courtType == "doubles" {
		expectedPerTeam = 2
	}
	if len(team1IDs) != expectedPerTeam || len(team2IDs) != expectedPerTeam {
		return nil, fmt.Errorf("%s requires %d player(s) per team", courtType, expectedPerTeam)
	}

	allIDs := append(team1IDs, team2IDs...)
	seen := make(map[int]bool)
	for _, id := range allIDs {
		if seen[id] {
			return nil, fmt.Errorf("a player cannot appear on both teams")
		}
		seen[id] = true
	}

	if winnerTeam != 1 && winnerTeam != 2 {
		return nil, fmt.Errorf("invalid winner_team: must be 1 or 2")
	}

	tx, err := db.Begin()
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()

	for _, id := range allIDs {
		var exists int
		err := tx.QueryRow("SELECT 1 FROM members WHERE id = ?", id).Scan(&exists)
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("member id %d not found", id)
		}
		if err != nil {
			return nil, fmt.Errorf("check member: %w", err)
		}
	}

	result, err := tx.Exec("INSERT INTO matches (court_type, match_date, scores, winner_team) VALUES (?, ?, ?, ?)", courtType, matchDate, scores, winnerTeam)
	if err != nil {
		return nil, fmt.Errorf("insert match: %w", err)
	}
	matchID, _ := result.LastInsertId()

	for _, mid := range team1IDs {
		_, err := tx.Exec("INSERT INTO match_players (match_id, member_id, team) VALUES (?, ?, 1)", matchID, mid)
		if err != nil {
			return nil, fmt.Errorf("insert team1 player: %w", err)
		}
	}
	for _, mid := range team2IDs {
		_, err := tx.Exec("INSERT INTO match_players (match_id, member_id, team) VALUES (?, ?, 2)", matchID, mid)
		if err != nil {
			return nil, fmt.Errorf("insert team2 player: %w", err)
		}
	}

	if err := tx.Commit(); err != nil {
		return nil, err
	}

	team1, _ := getTeamMembers(int(matchID), 1)
	team2, _ := getTeamMembers(int(matchID), 2)

	return &Match{
		ID:         int(matchID),
		CourtType:  courtType,
		MatchDate:  matchDate,
		Scores:     scores,
		WinnerTeam: winnerTeam,
		Team1:      team1,
		Team2:      team2,
	}, nil
}

func getTeamMembers(matchID, team int) ([]Member, error) {
	rows, err := db.Query(
		"SELECT m.id, m.nickname, m.level, m.join_date FROM members m JOIN match_players mp ON m.id = mp.member_id WHERE mp.match_id = ? AND mp.team = ?",
		matchID, team,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var members []Member
	for rows.Next() {
		var m Member
		if err := rows.Scan(&m.ID, &m.Nickname, &m.Level, &m.JoinDate); err != nil {
			return nil, err
		}
		members = append(members, m)
	}
	return members, nil
}

func GetMatches() ([]Match, error) {
	rows, err := db.Query("SELECT id, court_type, match_date, scores, winner_team FROM matches ORDER BY match_date DESC, id DESC")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var matches []Match
	for rows.Next() {
		var m Match
		if err := rows.Scan(&m.ID, &m.CourtType, &m.MatchDate, &m.Scores, &m.WinnerTeam); err != nil {
			return nil, err
		}
		m.Team1, _ = getTeamMembers(m.ID, 1)
		m.Team2, _ = getTeamMembers(m.ID, 2)
		matches = append(matches, m)
	}
	return matches, nil
}

func GetLeaderboard() ([]LeaderboardEntry, error) {
	query := `
	SELECT m.id, m.nickname, m.level,
	       COALESCE(SUM(CASE WHEN mp.match_id IS NULL THEN 0 WHEN mp.team = mw.winner_team THEN 3 ELSE 1 END), 0) AS points,
	       COALESCE(SUM(CASE WHEN mp.match_id IS NULL THEN 0 WHEN mp.team = mw.winner_team THEN 1 ELSE 0 END), 0) AS wins,
	       COALESCE(SUM(CASE WHEN mp.match_id IS NULL THEN 0 WHEN mp.team != mw.winner_team THEN 1 ELSE 0 END), 0) AS losses
	FROM members m
	LEFT JOIN match_players mp ON m.id = mp.member_id
	LEFT JOIN matches mw ON mp.match_id = mw.id
	GROUP BY m.id, m.nickname, m.level
	ORDER BY points DESC, wins DESC, m.nickname
	`
	rows, err := db.Query(query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var entries []LeaderboardEntry
	for rows.Next() {
		var e LeaderboardEntry
		if err := rows.Scan(&e.ID, &e.Nickname, &e.Level, &e.Points, &e.Wins, &e.Losses); err != nil {
			return nil, err
		}
		entries = append(entries, e)
	}
	return entries, nil
}

func GetMemberHistory(memberID int) (*MemberHistory, error) {
	member, err := GetMemberByID(memberID)
	if err != nil {
		return nil, err
	}
	if member == nil {
		return nil, nil
	}

	var wins, losses int
	err = db.QueryRow(`
		SELECT
			COALESCE(SUM(CASE WHEN mp.team = mw.winner_team THEN 1 ELSE 0 END), 0),
			COALESCE(SUM(CASE WHEN mp.team != mw.winner_team THEN 1 ELSE 0 END), 0)
		FROM match_players mp
		JOIN matches mw ON mp.match_id = mw.id
		WHERE mp.member_id = ?
	`, memberID).Scan(&wins, &losses)
	if err != nil {
		return nil, err
	}

	rows, err := db.Query(`
		SELECT m2.id, m2.nickname, COUNT(*) AS played
		FROM match_players mp1
		JOIN match_players mp2 ON mp1.match_id = mp2.match_id AND mp2.member_id != ?
		JOIN members m2 ON mp2.member_id = m2.id
		WHERE mp1.member_id = ?
		GROUP BY m2.id, m2.nickname
		ORDER BY played DESC, m2.nickname
	`, memberID, memberID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var opponents []OpponentStats
	for rows.Next() {
		var o OpponentStats
		if err := rows.Scan(&o.ID, &o.Nickname, &o.Played); err != nil {
			return nil, err
		}
		opponents = append(opponents, o)
	}

	return &MemberHistory{
		Member:    *member,
		Wins:      wins,
		Losses:    losses,
		Opponents: opponents,
	}, nil
}

func GetMostActiveThisMonth() (*ActiveMember, error) {
	now := time.Now()
	monthStart := time.Date(now.Year(), now.Month(), 1, 0, 0, 0, 0, now.Location()).Format("2006-01-02")

	var a ActiveMember
	err := db.QueryRow(`
		SELECT m.id, m.nickname, m.level, COUNT(*) AS cnt
		FROM match_players mp
		JOIN members m ON mp.member_id = m.id
		JOIN matches mw ON mp.match_id = mw.id
		WHERE mw.match_date >= ?
		GROUP BY m.id, m.nickname, m.level
		ORDER BY cnt DESC, m.nickname
		LIMIT 1
	`, monthStart).Scan(&a.ID, &a.Nickname, &a.Level, &a.MatchesThisMonth)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &a, nil
}
