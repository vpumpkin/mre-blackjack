#include "Core/ManhuntHUD.h"
#include "Core/ManhuntPlayerController.h"
#include "Core/ManhuntPlayerState.h"
#include "Core/ManhuntGameState.h"
#include "Core/ManhuntCharacter.h"
#include "Hunters/ManhuntHackerComponent.h"
#include "Hunters/ManhuntTrackerComponent.h"
#include "Hunters/ManhuntCCTVCamera.h"
#include "World/ManhuntExtractionPoint.h"
#include "EngineUtils.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"

namespace
{
	FString FormatTime(int32 Seconds)
	{
		return FString::Printf(TEXT("%02d:%02d"), FMath::Max(0, Seconds) / 60, FMath::Max(0, Seconds) % 60);
	}

	const FLinearColor ColText(0.95f, 0.95f, 0.95f);
	const FLinearColor ColRed(1.f, 0.15f, 0.1f);
	const FLinearColor ColYellow(1.f, 0.85f, 0.2f);
	const FLinearColor ColGreen(0.3f, 1.f, 0.4f);
	const FLinearColor ColBack(0.f, 0.f, 0.f, 0.55f);
}

void AManhuntHUD::DrawLine(const FString& Text, float X, float& Y, const FLinearColor& Color, float Scale)
{
	DrawText(Text, Color, X, Y, GEngine->GetMediumFont(), Scale);
	Y += 20.f * Scale;
}

void AManhuntHUD::DrawBar(float X, float Y, float W, float H, float Ratio, const FLinearColor& Color)
{
	DrawRect(ColBack, X - 2.f, Y - 2.f, W + 4.f, H + 4.f);
	DrawRect(Color, X, Y, W * FMath::Clamp(Ratio, 0.f, 1.f), H);
}

FVector2D AManhuntHUD::WorldToTablet(const FVector2D& World, float X, float Y, float Size) const
{
	// UE: +X = Norden (oben), +Y = Osten (rechts)
	const float U = 0.5f + (World.Y - MapCenter.Y) / (2.f * MapHalfSize);
	const float V = 0.5f - (World.X - MapCenter.X) / (2.f * MapHalfSize);
	return FVector2D(X + FMath::Clamp(U, 0.f, 1.f) * Size, Y + FMath::Clamp(V, 0.f, 1.f) * Size);
}

void AManhuntHUD::DrawTablet(AManhuntPlayerController* PC, float X, float Y, float Size)
{
	DrawRect(FLinearColor(0.02f, 0.05f, 0.08f, 0.8f), X, Y, Size, Size);
	DrawText(TEXT("TAKTIK-TABLET"), ColYellow, X + 6.f, Y + 4.f, GEngine->GetSmallFont());

	const float Now = GetWorld()->GetTimeSeconds();
	for (const FManhuntRunnerPing& Ping : PC->GetLastPings())
	{
		const FVector2D P = WorldToTablet(Ping.Location, X, Y, Size);
		const FLinearColor Col = Ping.Type == EManhuntPingType::Speedhunt ? ColRed : (Ping.Type == EManhuntPingType::Finale ? ColYellow : ColGreen);

		if (!Ping.BuildingName.IsNone())
		{
			// Gebaeude im 2D-Grundriss markieren (kein Stockwerk!)
			const float W = FMath::Max(6.f, Ping.BuildingExtent.Y / MapHalfSize * Size);
			const float H = FMath::Max(6.f, Ping.BuildingExtent.X / MapHalfSize * Size);
			DrawRect(FLinearColor(Col.R, Col.G, Col.B, 0.35f), P.X - W * 0.5f, P.Y - H * 0.5f, W, H);
		}
		DrawRect(Col, P.X - 4.f, P.Y - 4.f, 8.f, 8.f);

		const FString Name = Ping.Runner ? Ping.Runner->GetPlayerName() : TEXT("?");
		const FString Where = Ping.BuildingName.IsNone() ? FString() : FString::Printf(TEXT(" [%s]"), *Ping.BuildingName.ToString());
		DrawText(FString::Printf(TEXT("%s%s vor %ds"), *Name, *Where, FMath::RoundToInt(Now - PC->GetLastPingTime())),
			ColText, P.X + 6.f, P.Y - 6.f, GEngine->GetSmallFont());
	}

	if (const APawn* Pawn = PC->GetPawn())
	{
		const FVector2D Me = WorldToTablet(FVector2D(Pawn->GetActorLocation()), X, Y, Size);
		DrawRect(FLinearColor::White, Me.X - 3.f, Me.Y - 3.f, 6.f, 6.f);
	}
}

void AManhuntHUD::DrawHUD()
{
	Super::DrawHUD();

	AManhuntPlayerController* PC = Cast<AManhuntPlayerController>(GetOwningPlayerController());
	const AManhuntGameState* GS = GetWorld()->GetGameState<AManhuntGameState>();
	if (!PC || !GS || !Canvas)
	{
		return;
	}
	const AManhuntPlayerState* PS = PC->GetPlayerState<AManhuntPlayerState>();
	const AManhuntCharacter* Char = Cast<AManhuntCharacter>(PC->GetPawn());
	const float SW = Canvas->ClipX;
	const float SH = Canvas->ClipY;
	const bool bRunner = PS && PS->GetTeam() == EManhuntTeam::Runner;
	const bool bHunter = PS && PS->GetTeam() == EManhuntTeam::Hunter;

	// ---------------- Oben Mitte: Phase & Zeit ----------------
	FString Top;
	switch (GS->GetPhase())
	{
	case EManhuntPhase::WaitingForPlayers: Top = FString::Printf(TEXT("WARTE AUF SPIELER (%d)"), GS->PlayerArray.Num()); break;
	case EManhuntPhase::ClassSelection:    Top = FString::Printf(TEXT("KLASSENWAHL  %d s"), FMath::CeilToInt(GS->GetClassSelectionRemaining())); break;
	case EManhuntPhase::Hunt:              Top = FString::Printf(TEXT("JAGD  %s"), *FormatTime(GS->GetRemainingSeconds())); break;
	case EManhuntPhase::Finale:            Top = FString::Printf(TEXT("FINALE  %s"), *FormatTime(GS->GetRemainingSeconds())); break;
	case EManhuntPhase::Ended:             Top = GS->GetWinningTeam() == EManhuntTeam::Runner ? TEXT("RUNNER GEWINNEN") : TEXT("HUNTER GEWINNEN"); break;
	}
	const float Hour = GS->GetTimeOfDayHours();
	Top += FString::Printf(TEXT("   |   %02d:%02d Uhr"), FMath::FloorToInt(Hour), FMath::FloorToInt(FMath::Frac(Hour) * 60.f));
	DrawRect(ColBack, SW * 0.5f - 210.f, 8.f, 420.f, 34.f);
	DrawText(Top, ColText, SW * 0.5f - 195.f, 14.f, GEngine->GetMediumFont(), 1.1f);

	if (GS->IsSpeedhuntActive())
	{
		DrawText(bRunner ? TEXT("SPEEDHUNT AKTIV!") : TEXT("Speedhunt laeuft"), ColRed, SW * 0.5f - 120.f, 50.f, GEngine->GetLargeFont(), bRunner ? 1.4f : 1.f);
	}

	// ---------------- Oben links: Team, Klasse, Inventar ----------------
	float Y = 12.f;
	if (PS)
	{
		if (bRunner)
		{
			DrawLine(TEXT("RUNNER"), 16.f, Y, ColGreen, 1.2f);
			DrawLine(FString::Printf(TEXT("Geld: %s"), *ManhuntMoney::Format(PS->GetMoneyCents())), 16.f, Y, ColText);
			DrawLine(FString::Printf(TEXT("Pfandbon: %s"), *ManhuntMoney::Format(PS->GetPfandbonCents())), 16.f, Y, ColText);
			DrawLine(FString::Printf(TEXT("Pfandflaschen: %d"), PS->GetBottleCount()), 16.f, Y, ColText);
			DrawLine(FString::Printf(TEXT("[1] Energy-Drink x%d  [2] Ping-Blocker x%d  [3] Fake-Ping x%d"),
				PS->GetItemCount(EManhuntItem::EnergyDrink), PS->GetItemCount(EManhuntItem::PingBlocker), PS->GetItemCount(EManhuntItem::FakePing)), 16.f, Y, ColText, 0.9f);
			DrawLine(TEXT("[Q] Tuer verriegeln/entriegeln"), 16.f, Y, ColText, 0.9f);
		}
		else if (bHunter)
		{
			const UEnum* ClassEnum = StaticEnum<EHunterClass>();
			const FString ClassName = ClassEnum ? ClassEnum->GetDisplayNameTextByValue(static_cast<int64>(PS->GetHunterClass())).ToString() : FString();
			DrawLine(FString::Printf(TEXT("HUNTER - %s%s"), *ClassName, PS->IsTaskforceLeader() ? TEXT("  (Taskforce-Leader)") : TEXT("")), 16.f, Y, ColRed, 1.2f);
			if (GS->GetPhase() == EManhuntPhase::ClassSelection || GS->GetPhase() == EManhuntPhase::WaitingForPlayers)
			{
				DrawLine(TEXT("Klasse waehlen: [1] Hacker  [2] Kampfsportler  [3] Faehrtenleser"), 16.f, Y, ColYellow);
			}
			if (PS->IsTaskforceLeader())
			{
				const AManhuntPlayerState* Sel = PC->GetSpeedhuntSelection();
				DrawLine(FString::Printf(TEXT("Speedhunts uebrig: %d   Ziel [J]: %s   Start [H]"),
					GS->GetSpeedhuntsRemaining(), Sel ? *Sel->GetPlayerName() : TEXT("-")), 16.f, Y, ColText, 0.9f);
			}
			if (Char && Char->Hacker && PS->GetHunterClass() == EHunterClass::Hacker)
			{
				DrawLine(TEXT("[Q] Ueberwachungskameras  [Mausrad] Kamera wechseln"), 16.f, Y, ColText, 0.9f);
			}
			if (Char && Char->Tracker && PS->GetHunterClass() == EHunterClass::Tracker)
			{
				const float CD = Char->Tracker->GetCooldownRemaining();
				DrawLine(CD > 0.f ? FString::Printf(TEXT("[Q] Spuren lesen: %d s"), FMath::CeilToInt(CD)) : FString(TEXT("[Q] Spuren lesen: BEREIT")), 16.f, Y, CD > 0.f ? ColText : ColGreen, 0.9f);
			}
			DrawLine(TEXT("[LMB] Tackle   [Tab] Tablet"), 16.f, Y, ColText, 0.9f);
		}
	}

	// ---------------- Unten: Stamina, Hinweis, Fortschritt ----------------
	if (Char)
	{
		DrawText(TEXT("Stamina"), ColText, 16.f, SH - 52.f, GEngine->GetSmallFont());
		DrawBar(16.f, SH - 34.f, 260.f, 14.f, Char->GetStaminaRatio(), Char->GetStaminaRatio() > 0.25f ? ColGreen : ColRed);

		const FText Prompt = Char->GetFocusPrompt();
		if (!Prompt.IsEmpty())
		{
			const FString PromptText = Char->GetGrabbedBy() ? Prompt.ToString() : FString::Printf(TEXT("[E] %s"), *Prompt.ToString());
			DrawText(PromptText, ColYellow, SW * 0.5f - 120.f, SH * 0.62f, GEngine->GetMediumFont(), 1.2f);
		}
		const float Progress = Char->GetTimedActionProgress();
		if (Progress > 0.f)
		{
			DrawText(Char->GetTimedActionLabel().ToString(), ColText, SW * 0.5f - 150.f, SH * 0.68f, GEngine->GetSmallFont());
			DrawBar(SW * 0.5f - 150.f, SH * 0.68f + 18.f, 300.f, 10.f, Progress, ColYellow);
		}
		if (Char->GetGrabbedBy() || Char->GetGrabbedRunner())
		{
			const AManhuntCharacter* Runner = Char->GetGrabbedBy() ? Char : Char->GetGrabbedRunner();
			DrawText(TEXT("STRUGGLE"), ColRed, SW * 0.5f - 40.f, SH * 0.72f, GEngine->GetMediumFont());
			DrawBar(SW * 0.5f - 150.f, SH * 0.72f + 22.f, 300.f, 14.f, Runner->GetStruggleProgress(), ColRed);
		}
		if (Char->Hacker && Char->Hacker->IsViewingCCTV())
		{
			const AManhuntCCTVCamera* Cam = Char->Hacker->GetActiveCamera();
			DrawRect(ColRed, 24.f, SH * 0.5f - 6.f, 12.f, 12.f);
			DrawText(FString::Printf(TEXT("REC  %s   [Mausrad] wechseln  [Q] beenden"), Cam ? *Cam->DisplayName.ToString() : TEXT("")),
				ColText, 44.f, SH * 0.5f - 10.f, GEngine->GetMediumFont());
		}
	}

	// ---------------- Rechts: Nachrichten ----------------
	float MY = 60.f;
	const float Now = GetWorld()->GetTimeSeconds();
	for (const FManhuntHudMessage& Msg : PC->GetMessages())
	{
		if (Msg.ExpireTime >= Now)
		{
			DrawText(Msg.Text.ToString(), ColText, SW - 520.f, MY, GEngine->GetSmallFont(), 1.1f);
			MY += 20.f;
		}
	}

	// ---------------- Faehrtenleser: Alter der frischesten Spur ----------------
	if (Char && Char->Tracker && Char->Tracker->GetNewestTrackAge() >= 0.f)
	{
		DrawText(FString::Printf(TEXT("Frischeste Spur: %d s alt"), FMath::RoundToInt(Char->Tracker->GetNewestTrackAge())),
			ColRed, SW * 0.5f - 90.f, 80.f, GEngine->GetMediumFont(), 1.1f);
	}

	// ---------------- Finale: aktive Extraktionspunkte ----------------
	if (GS->GetPhase() == EManhuntPhase::Finale && Char)
	{
		for (TActorIterator<AManhuntExtractionPoint> It(GetWorld()); It; ++It)
		{
			if (!It->IsExtractionActive())
			{
				continue;
			}
			const FVector Screen = Project(It->GetActorLocation() + FVector(0.f, 0.f, 300.f));
			if (Screen.Z > 0.f)
			{
				const int32 Meters = FMath::RoundToInt(FVector::Dist(It->GetActorLocation(), Char->GetActorLocation()) / 100.f);
				DrawText(FString::Printf(TEXT("EXTRAKTION %s  %d m"), *It->DisplayName.ToString(), Meters),
					ColYellow, Screen.X - 80.f, Screen.Y, GEngine->GetMediumFont());
			}
		}
	}

	// ---------------- Taktik-Tablet (nur Hunter) ----------------
	if (bHunter)
	{
		if (PC->IsTabletOpen())
		{
			const float Size = FMath::Min(SW, SH) * 0.7f;
			DrawTablet(PC, (SW - Size) * 0.5f, (SH - Size) * 0.5f, Size);
		}
		else
		{
			DrawTablet(PC, SW - 236.f, SH - 236.f, 220.f);
		}
	}
}
