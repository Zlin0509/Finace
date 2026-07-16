package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Zlin0509/Finace/internal/server"
	"github.com/Zlin0509/Finace/internal/storage"
)

func main() {
	command := "serve"
	if len(os.Args) > 1 && !isFlag(os.Args[1]) {
		command = os.Args[1]
		os.Args = append([]string{os.Args[0]}, os.Args[2:]...)
	}
	database := flag.String("db", env("FUNDMASTER_DATABASE_PATH", "data/fundmaster.db"), "SQLite database path")
	backupDir := flag.String("backups", env("FUNDMASTER_BACKUP_PATH", "data/backups"), "backup directory")
	legacy := flag.String("legacy", env("FUNDMASTER_LEGACY_PORTFOLIO_PATH", "data/portfolio.json"), "legacy portfolio JSON")
	address := flag.String("addr", env("FUNDMASTER_ADDR", "127.0.0.1:8503"), "HTTP listen address")
	flag.Parse()
	if command == "version" {
		fmt.Println("FundMaster Pro", server.Version, "(Go)")
		return
	}
	store, err := storage.Open(*database, *backupDir)
	if err != nil {
		log.Fatal(err)
	}
	defer store.Close()
	if migrated, err := store.MigrateLegacy(context.Background(), *legacy); err != nil {
		log.Fatal(err)
	} else if migrated > 0 {
		log.Printf("migrated %d legacy transactions", migrated)
	}
	if command == "backup" {
		path, err := store.Backup(context.Background())
		if err != nil {
			log.Fatal(err)
		}
		fmt.Println(path)
		return
	}
	if command != "serve" {
		log.Fatalf("unknown command %q", command)
	}
	_, _ = store.BackupIfDue(context.Background(), 24*time.Hour)
	logger := log.New(os.Stdout, "fundmaster ", log.LstdFlags)
	app := server.New(store, logger)
	httpServer := &http.Server{Addr: *address, Handler: app.Handler(), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 20 * time.Second, WriteTimeout: 60 * time.Second, IdleTimeout: 90 * time.Second}
	go func() {
		logger.Printf("Go workbench v%s running at http://%s", server.Version, *address)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatal(err)
		}
	}()
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	_ = httpServer.Shutdown(ctx)
}

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
func isFlag(value string) bool { return len(value) > 0 && value[0] == '-' }
