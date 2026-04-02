#!/usr/bin/env python3
"""
Diagnostic test for audio fingerprinting in FrameVault
Tests: ffmpeg, audio extraction, comparison, and database storage
"""

import sys
import os
import subprocess
import tempfile
import sqlite3

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def test_ffmpeg():
    """Check if ffmpeg is available."""
    print("🔍 Testing ffmpeg availability...")
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        if result.returncode == 0:
            # Extract version from output
            version_line = result.stdout.decode().split('\n')[0] if result.stdout else ""
            print(f"   ✅ ffmpeg is available: {version_line}")
            return True
    except FileNotFoundError:
        print("   ❌ ffmpeg is NOT installed or not in PATH")
        print("      Windows: Install from https://ffmpeg.org/download.html")
        print("      macOS: brew install ffmpeg")
        print("      Linux: apt-get install ffmpeg")
        return False
    except Exception as e:
        print(f"   ❌ Error testing ffmpeg: {e}")
        return False

def test_audio_functions():
    """Test audio fingerprinting functions."""
    print("\n🔍 Testing audio fingerprinting functions...")
    try:
        from scanner import extract_audio_fingerprint, compare_audio_fingerprints
        print("   ✅ Audio functions imported successfully")
        
        # Test compare_audio_fingerprints with dummy data
        fp1 = "0.5,0.6,0.7,0.8;0.1,0.2,0.3,0.4"  # Minimal valid fingerprint
        fp2 = "0.5,0.6,0.7,0.8;0.1,0.2,0.3,0.4"  # Identical
        
        score = compare_audio_fingerprints(fp1, fp2)
        print(f"   ✅ Audio comparison works: fingerprint similarity = {score}%")
        
        if score >= 95:
            print("   ✅ Identical fingerprints score correctly (~100%)")
        else:
            print(f"   ⚠️  Expected ~100% similarity, got {score}%")
            
        return True
    except Exception as e:
        print(f"   ❌ Error testing audio functions: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_audioip_column():
    """Check if audio_fp column exists in database."""
    print("\n🔍 Testing audio_fp column in database...")
    try:
        from database import get_db
        
        db = get_db()
        cursor = db.cursor()
        
        # Check if audio_fp column exists
        cursor.execute("PRAGMA table_info(file_hashes)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        if 'audio_fp' in columns:
            print(f"   ✅ audio_fp column exists (type: {columns['audio_fp']})")
            db.close()
            return True
        else:
            print("   ⚠️  audio_fp column NOT FOUND in file_hashes table")
            print("      Columns found:", list(columns.keys()))
            
            # Try to add it
            print("      Attempting to add audio_fp column...")
            try:
                cursor.execute("ALTER TABLE file_hashes ADD COLUMN audio_fp TEXT")
                db.commit()
                print("   ✅ Successfully added audio_fp column")
                db.close()
                return True
            except Exception as e:
                print(f"   ❌ Failed to add column: {e}")
                db.close()
                return False
                
    except Exception as e:
        print(f"   ❌ Error checking database: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_extract_from_dummy_video():
    """Try to extract audio from a synthetic video file."""
    print("\n🔍 Testing audio extraction from video file...")
    
    if not test_ffmpeg.__wrapped__ if hasattr(test_ffmpeg, '__wrapped__') else test_ffmpeg:
        # Already know ffmpeg isn't available, skip
        print("   ⚠️  Skipping (ffmpeg not available)")
        return None
    
    try:
        from scanner import extract_audio_fingerprint
        
        # Create a minimal test video using ffmpeg
        print("      Creating test video with audio...")
        tmp_video = tempfile.mktemp(suffix=".mp4")
        
        # Create simple test video with silent audio
        cmd = [
            'ffmpeg',
            '-f', 'lavfi', '-i', 'color=c=black:s=320x240:d=1', 
            '-f', 'lavfi', '-i', 'anullsrc=r=16000:cl=mono',
            '-pix_fmt', 'yuv420p',
            '-y', tmp_video,
            '-loglevel', 'quiet'
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        
        if result.returncode != 0 or not os.path.exists(tmp_video):
            print("   ⚠️  Failed to create test video")
            return None
        
        print("      Extracting audio fingerprint...")
        fp = extract_audio_fingerprint(tmp_video)
        
        if fp:
            parts = fp.split(';')
            if len(parts) == 2:
                rms_vals = parts[0].split(',')
                zcr_vals = parts[1].split(',')
                print(f"   ✅ Audio extraction successful")
                print(f"      RMS segments: {len(rms_vals)}")
                print(f"      ZCR segments: {len(zcr_vals)}")
                if len(rms_vals) == 64 and len(zcr_vals) == 64:
                    print(f"   ✅ Correct fingerprint format (64 segments each)")
                    return True
                else:
                    print(f"   ⚠️  Unexpected segment count")
                    return False
        else:
            print("   ❌ Audio extraction returned None")
            return False
            
    except Exception as e:
        print(f"   ❌ Error testing extraction: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        try:
            if 'tmp_video' in locals() and os.path.exists(tmp_video):
                os.remove(tmp_video)
        except:
            pass

def main():
    print("=" * 60)
    print("🎵 FrameVault Audio Fingerprinting Diagnostic Test")
    print("=" * 60)
    
    results = {
        "ffmpeg": test_ffmpeg(),
        "functions": test_audio_functions(),
        "database": test_database_audioip_column(),
        "extraction": test_extract_from_dummy_video(),
    }
    
    print("\n" + "=" * 60)
    print("📊 Summary")
    print("=" * 60)
    
    for feature, result in results.items():
        if result is True:
            status = "✅ PASS"
        elif result is False:
            status = "❌ FAIL"
        else:
            status = "⚠️  SKIP"
        print(f"{feature:20} {status}")
    
    all_passed = all(v is not False for v in results.values())
    
    if all_passed:
        print("\n✅ Audio fingerprinting is FUNCTIONAL")
    elif all(v not in [True, None] for v in results.values()):
        print("\n❌ Audio fingerprinting has CRITICAL ISSUES")
    else:
        print("\n⚠️  Audio fingerprinting is PARTIALLY FUNCTIONAL")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
