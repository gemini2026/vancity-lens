output "archive_bucket_name" {
  description = "Document archive bucket name"
  value       = google_storage_bucket.archive.name
}

output "archive_bucket_url" {
  description = "Document archive bucket URL"
  value       = google_storage_bucket.archive.url
}

output "long_term_bucket_name" {
  description = "Long-term retention bucket name"
  value       = google_storage_bucket.long_term.name
}

output "long_term_bucket_url" {
  description = "Long-term retention bucket URL"
  value       = google_storage_bucket.long_term.url
}
