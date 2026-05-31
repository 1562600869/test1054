package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
)

func main() {
	port := flag.Int("port", 6274, "server port")
	flag.Parse()

	dbPath := "badminton.db"
	if err := InitDB(dbPath); err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}
	defer db.Close()

	mux := http.NewServeMux()

	mux.HandleFunc("/api/members", membersHandler)
	mux.HandleFunc("/api/members/", memberHistoryHandler)
	mux.HandleFunc("/api/matches", matchesHandler)
	mux.HandleFunc("/api/leaderboard", leaderboardHandler)
	mux.HandleFunc("/api/active", activeMemberHandler)

	fs := http.FileServer(http.Dir("./static"))
	mux.Handle("/", fs)

	addr := fmt.Sprintf(":%d", *port)
	log.Printf("🏸 Badminton Club server starting on http://localhost%s", addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
